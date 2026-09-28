import { useLayoutEffect } from "react";
import { Empty } from "../../components/common";
import {
  metricLabel,
  pageNumber,
  resultRows,
  score,
  taskDomain,
  taskLabel,
  type ViewParams,
} from "./presentation";
import type { BatchDetail } from "./types";
import { csv, download, duration, link, number, outcome } from "./utils";

export function BatchResults({
  batch,
  metric,
  params,
  update,
}: {
  batch: BatchDetail;
  metric: string;
  params: ViewParams;
  update: (values: Record<string, string | null>) => void;
}) {
  const rows = resultRows(batch.runs, metric, params);
  const size = params.size === "50" ? 50 : 20;
  const current = pageNumber(params.page, rows.length, size);
  const domains = [
    ...new Set(batch.runs.map((r) => taskDomain(r.unit_id)).filter(Boolean)),
  ];
  const scrollKey = `bench-scroll-${batch.id}`;
  useLayoutEffect(() => {
    const saved = sessionStorage.getItem(scrollKey);
    if (saved != null) {
      window.scrollTo(0, Number(saved) || 0);
      sessionStorage.removeItem(scrollKey);
    }
  }, [scrollKey]);
  const change = (values: Record<string, string | null>) =>
    update({ ...values, page: null });
  return (
    <section aria-label="任务结果" className="batch-results">
      <h2 className="sr-only">任务结果</h2>
      {batch.duplicate_tasks && (
        <p className="bench-warning">
          本组包含同任务的多次尝试，逐项保留；不会自动挑选最高分。
        </p>
      )}
      <div className="bench-filters result-filters">
        <label className="search-field">
          搜索任务
          <input
            type="search"
            placeholder="任务名称、领域或笔记"
            value={params.search ?? ""}
            onChange={(e) => change({ search: e.target.value })}
          />
        </label>
        {domains.length > 0 && (
          <label>
            领域
            <select
              value={params.domain ?? ""}
              onChange={(e) => change({ domain: e.target.value })}
            >
              <option value="">全部领域</option>
              {domains.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          结果筛选
          <select
            value={params.filter ?? "all"}
            onChange={(e) => change({ filter: e.target.value })}
          >
            <option value="all">全部任务</option>
            <option value="evaluation">评分需要复核</option>
            <option value="solver">求解异常结束</option>
            <option value="conflict">状态记录冲突</option>
            <option value="zero">零分任务</option>
            <option value="failed">失败与超时</option>
            <option value="unscored">无有效评分</option>
            <option value="running">运行中</option>
            <option value="queued">排队中</option>
            <option value="not_submitted">未提交</option>
            <option value="cancelled">已取消</option>
            <option value="cleanup">清理未完成</option>
          </select>
        </label>
        <label>
          任务排序
          <select
            value={params.sort ?? "score"}
            onChange={(e) => change({ sort: e.target.value })}
          >
            <option value="score">得分从低到高</option>
            <option value="high">得分从高到低</option>
            <option value="duration">耗时从长到短</option>
            <option value="task">任务名称</option>
          </select>
        </label>
      </div>
      <div className="section-line result-count">
        <small role="status">
          {rows.length} / {batch.total} 个任务 · 筛选不改变实验均分
        </small>
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
                  "evaluation_health",
                  "solver_terminal",
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
                  r.health?.evaluation.status,
                  r.health?.solver.status,
                  score(r, metric),
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
      </div>
      {rows.length ? (
        <div className="table-wrap workbench-table bench-result-table">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                {domains.length > 0 && <th>领域</th>}
                <th className="numeric">{metricLabel(metric)}</th>
                <th>结果</th>
                <th className="numeric">运行耗时</th>
                <th>
                  <span className="sr-only">查看详情</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows
                .slice(current * size, (current + 1) * size)
                .map((run, i) => {
                  const href = link({
                    ...params,
                    batch: batch.id,
                    run: run.run_id,
                    view: null,
                    step: null,
                    cursor: null,
                  });
                  const saveScroll = () =>
                    sessionStorage.setItem(scrollKey, String(window.scrollY));
                  return (
                    <tr key={run.run_id ?? `${run.unit_id}-${i}`}>
                      <th scope="row">
                        <a
                          href={run.run_id ? href : undefined}
                          onClick={saveScroll}
                          title={run.unit_id}
                        >
                          {taskLabel(run.unit_id)}
                        </a>
                        {run.annotation.notes && (
                          <small title={run.annotation.notes}>有实验笔记</small>
                        )}
                      </th>
                      {domains.length > 0 && (
                        <td>{taskDomain(run.unit_id) || "—"}</td>
                      )}
                      <td className="numeric score-value">
                        {number(score(run, metric))}
                      </td>
                      <td>
                        <span
                          className={`result-state ${["failed", "timed_out"].includes(run.execution ?? "") ? "result-failed" : ""}`}
                        >
                          {outcome(run)}
                        </span>
                        {run.health?.evaluation.status === "needs_review" && (
                          <small>评分需复核</small>
                        )}
                        {run.health?.solver.status === "quota_exhausted" && (
                          <small>额度耗尽中断</small>
                        )}
                        {run.health?.solver.status === "failed" && (
                          <small>求解异常结束</small>
                        )}
                        {run.cleanup_complete === false && (
                          <small>清理未完成</small>
                        )}
                        {run.failure_reason && (
                          <small
                            className="bench-reason"
                            title={run.failure_reason}
                          >
                            {run.failure_reason}
                          </small>
                        )}
                      </td>
                      <td className="numeric muted">
                        {duration(run.elapsed_seconds)}
                      </td>
                      <td>
                        {run.run_id ? (
                          <a href={href} onClick={saveScroll}>
                            查看详情
                          </a>
                        ) : (
                          "等待提交"
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>
          没有匹配的任务。
          <button
            type="button"
            onClick={() => change({ search: null, filter: null, domain: null })}
          >
            清除筛选
          </button>
        </Empty>
      )}
      <div className="table-pagination">
        <label className="inline">
          每页
          <select
            value={size}
            onChange={(e) => change({ size: e.target.value })}
          >
            <option value="20">20 条</option>
            <option value="50">50 条</option>
          </select>
        </label>
        <div className="actions">
          <button
            type="button"
            disabled={current === 0}
            onClick={() => update({ page: String(current - 1) })}
          >
            上一页任务
          </button>
          <span>
            {current + 1} / {Math.max(1, Math.ceil(rows.length / size))}
          </span>
          <button
            type="button"
            disabled={(current + 1) * size >= rows.length}
            onClick={() => update({ page: String(current + 1) })}
          >
            下一页任务
          </button>
        </div>
      </div>
    </section>
  );
}
