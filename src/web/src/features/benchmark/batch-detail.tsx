import { useState } from "react";
import { Empty, Panel } from "../../components/common";
import { Notes } from "./notes";
import type { BatchDetail } from "./types";
import {
  csv,
  download,
  duration,
  link,
  number,
  outcome,
  stateLabels,
} from "./utils";

export function BatchResults({
  token,
  batch,
  metric,
  baseline,
  saved,
}: {
  token: string;
  batch: BatchDetail;
  metric: string;
  baseline: string;
  saved: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("task");
  const [page, setPage] = useState(0);
  const rows = batch.runs
    .filter(
      (r) =>
        `${r.unit_id} ${r.model} ${r.annotation.notes ?? ""}`
          .toLowerCase()
          .includes(search.toLowerCase()) &&
        (filter === "all" ||
          (filter === "unscored"
            ? !r.score_valid
            : filter === "failed"
              ? r.execution === "failed" || r.execution === "timed_out"
              : r.state === filter)),
    )
    .sort((a, b) =>
      sort === "score"
        ? (a.metrics[metric] ?? Infinity) - (b.metrics[metric] ?? Infinity)
        : sort === "duration"
          ? (b.elapsed_seconds ?? -1) - (a.elapsed_seconds ?? -1)
          : a.unit_id.localeCompare(b.unit_id),
    );
  const current = Math.min(page, Math.max(0, Math.ceil(rows.length / 50) - 1));
  const failed = batch.runs.filter((r) => r.failure_reason);
  const reasons = new Map<string, number>();
  for (const run of failed) {
    const reason = run.failure_reason as string;
    reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
  }
  return (
    <>
      {batch.duplicate_tasks && (
        <p className="bench-warning">
          本组包含同任务的多次尝试，逐项保留；不会自动挑选最高分参与比较或趋势。
        </p>
      )}
      <Notes
        key={batch.id}
        token={token}
        batch={batch.id}
        initial={batch.annotation}
        saved={saved}
      />
      <div className="bench-status-line">
        {Object.entries(batch.states).map(([state, count]) => (
          <span key={state}>
            {stateLabels[state] ?? state} <strong>{count}</strong>
          </span>
        ))}
        <small>
          最近活动：
          {batch.updated_at
            ? new Date(batch.updated_at).toLocaleString()
            : "尚未提交"}
        </small>
      </div>
      {reasons.size > 0 && (
        <details className="bench-warning">
          <summary>{failed.length} 个任务有失败或诊断信息</summary>
          {[...reasons]
            .sort((a, b) => b[1] - a[1])
            .map(([reason, count]) => (
              <p key={reason}>
                {count} 项 · {reason}
              </p>
            ))}
        </details>
      )}
      <Panel title="任务结果">
        <div className="bench-filters">
          <label>
            搜索任务
            <input
              type="search"
              placeholder="任务名称、模型或笔记"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <label>
            结果筛选
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="all">全部任务</option>
              <option value="failed">失败与超时</option>
              <option value="unscored">无有效评分</option>
              <option value="running">运行中</option>
              <option value="queued">排队中</option>
              <option value="not_submitted">未提交</option>
            </select>
          </label>
          <label>
            任务排序
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value);
                setPage(0);
              }}
            >
              <option value="task">任务名称</option>
              <option value="score">低分优先</option>
              <option value="duration">耗时最长</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() =>
              download(
                "benchmark-results.csv",
                csv([
                  [
                    "task",
                    "model",
                    "state",
                    "execution",
                    "evaluation",
                    metric,
                    "elapsed_seconds",
                    "run_id",
                    "notes",
                  ],
                  ...rows.map((r) => [
                    r.unit_id,
                    r.model,
                    r.state,
                    r.execution,
                    r.evaluation,
                    r.score_valid ? r.metrics[metric] : null,
                    r.elapsed_seconds,
                    r.run_id,
                    r.annotation.notes,
                  ]),
                ]),
                "text/csv;charset=utf-8",
              )
            }
          >
            导出结果 CSV
          </button>
          <button
            type="button"
            onClick={() =>
              download(
                "benchmark-experiment.md",
                `# ${batch.name}\n\n${batch.annotation.notes ?? ""}\n\n模型：${batch.models.join(", ")}\n\n已结束 ${batch.finished}/${batch.total}；有效评分 ${batch.scored}/${batch.total}\n\n${metric}：${number(batch.metrics[metric]?.mean)}（已评分任务描述性均值，不是官方总分）\n\n${location.href}\n`,
              )
            }
          >
            导出实验摘要
          </button>
        </div>
        <small>
          {rows.length} / {batch.total} 个任务 · 每页 50 条，所有成员均可查询
        </small>
        {rows.length ? (
          <div className="table-wrap bench-result-table">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>结果</th>
                  <th>{metric || "得分"}</th>
                  <th>耗时 / 预算</th>
                  <th>模型</th>
                  <th>复盘</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(current * 50, (current + 1) * 50).map((run, i) => (
                  <tr key={run.run_id ?? `${run.unit_id}-${i}`}>
                    <td>
                      {run.unit_id}
                      {run.annotation.notes && (
                        <small title={run.annotation.notes}>有实验笔记</small>
                      )}
                    </td>
                    <td>
                      {outcome(run)}
                      {run.failure_reason && (
                        <small
                          className="bench-reason"
                          title={run.failure_reason}
                        >
                          {run.failure_reason}
                        </small>
                      )}
                    </td>
                    <td>
                      {number(run.score_valid ? run.metrics[metric] : null)}
                    </td>
                    <td>
                      {duration(run.elapsed_seconds)}
                      <small>预算 {duration(run.budget_seconds)}</small>
                    </td>
                    <td>{run.model}</td>
                    <td>
                      {run.run_id ? (
                        <a
                          href={link({
                            batch: batch.id,
                            run: run.run_id,
                            baseline,
                            metric,
                          })}
                        >
                          查看详情
                        </a>
                      ) : (
                        "等待提交"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>没有匹配的任务，试试调整筛选条件。</Empty>
        )}
        <div className="actions">
          <button
            type="button"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            上一页任务
          </button>
          <span>
            {current + 1} / {Math.max(1, Math.ceil(rows.length / 50))}
          </span>
          <button
            type="button"
            disabled={(current + 1) * 50 >= rows.length}
            onClick={() => setPage(current + 1)}
          >
            下一页任务
          </button>
        </div>
      </Panel>
    </>
  );
}
