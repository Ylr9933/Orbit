import { useState } from "react";
import { useData } from "../../api/console";
import { Notice, Panel } from "../../components/common";
import { ScoreMatrix } from "./charts";
import type { Batch, Comparison } from "./types";
import {
  comparisonCsv,
  configDiff,
  download,
  link,
  number,
  workspace,
} from "./utils";

export function ComparisonPanel({
  token,
  baseline,
  candidate,
  metric,
}: {
  token: string;
  baseline: Batch;
  candidate: Batch;
  metric: string;
}) {
  const { data, error } = useData<Comparison>(
    token,
    `${workspace}/compare?${new URLSearchParams({ left: baseline.id, right: candidate.id, metric })}`,
    baseline.finished === baseline.total &&
      candidate.finished === candidate.total
      ? 0
      : 5000,
  );
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState("maximize");
  const [sort, setSort] = useState("regression");
  const rows =
    data?.rows
      .filter((r) => r.unit_id.toLowerCase().includes(search.toLowerCase()))
      .sort((a, b) => {
        if (sort === "task") return a.unit_id.localeCompare(b.unit_id);
        if (a.delta == null) return b.delta == null ? 0 : 1;
        if (b.delta == null) return -1;
        return (
          (a.delta - b.delta) *
          (sort === "improvement" ? -1 : 1) *
          (direction === "minimize" ? -1 : 1)
        );
      }) ?? [];
  const sample = data?.rows.find((r) => r.left && r.right);
  const differences = sample
    ? configDiff(sample.left?.config, sample.right?.config)
    : [];
  return (
    <Panel title="与基线比较">
      <p>
        {baseline.name} → {candidate.name}
      </p>
      <Notice error={error} loading={!data} />
      {data && (
        <>
          <div className="bench-comparison-stats">
            <span>
              可比任务{" "}
              <strong>
                {data.paired} / {data.total}
              </strong>
            </span>
            <span>
              基线均值 <strong>{number(data.left_mean)}</strong>
            </span>
            <span>
              当前均值 <strong>{number(data.right_mean)}</strong>
            </span>
            <span>
              均值变化 <strong>{number(data.mean_delta)}</strong>
            </span>
          </div>
          <p className="muted">
            {data.aggregation}。仅使用两侧共同有效的任务；配置差异见下方。
          </p>
          <div className="bench-filters">
            <label>
              搜索对比任务
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              指标方向
              <select
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
              >
                <option value="maximize">越大越好</option>
                <option value="minimize">越小越好</option>
              </select>
            </label>
            <label>
              对比排序
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="regression">退步最多</option>
                <option value="improvement">提升最多</option>
                <option value="task">任务名称</option>
              </select>
            </label>
          </div>
          <div className="actions">
            <button
              type="button"
              onClick={() =>
                download(
                  "benchmark-comparison.csv",
                  comparisonCsv(data),
                  "text/csv;charset=utf-8",
                )
              }
            >
              导出对比 CSV
            </button>
            <button
              type="button"
              onClick={() =>
                download(
                  "benchmark-comparison.md",
                  `# ${baseline.name} → ${candidate.name}\n\n指标：${metric}\n\n${data.aggregation}\n\n可比任务：${data.paired}/${data.total}\n\n基线：${number(data.left_mean)}；当前：${number(data.right_mean)}；差值：${number(data.mean_delta)}\n\n${candidate.annotation.notes ?? ""}\n\n|任务|差值|说明|\n|---|---:|---|\n${data.rows.map((r) => `|${r.unit_id.replaceAll("|", "\\|")}|${number(r.delta)}|${r.reason ?? "可比"}|`).join("\n")}`,
                )
              }
            >
              导出比较摘要
            </button>
          </div>
          <div className="table-wrap bench-comparison-table">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>基线</th>
                  <th>当前</th>
                  <th>差值</th>
                  <th>复盘</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.unit_id}>
                    <td>
                      {row.unit_id}
                      {row.reason && <small>{row.reason}</small>}
                    </td>
                    <td>
                      {number(
                        row.left?.score_valid ? row.left.metrics[metric] : null,
                      )}
                    </td>
                    <td>
                      {number(
                        row.right?.score_valid
                          ? row.right.metrics[metric]
                          : null,
                      )}
                    </td>
                    <td
                      className={
                        row.delta == null
                          ? ""
                          : row.delta * (direction === "minimize" ? -1 : 1) < 0
                            ? "bench-negative"
                            : "bench-positive"
                      }
                    >
                      {number(row.delta)}
                    </td>
                    <td>
                      {row.left?.run_id && row.right?.run_id && (
                        <a
                          href={link({
                            batch: candidate.id,
                            run: row.right.run_id,
                            peerBatch: baseline.id,
                            peer: row.left.run_id,
                            baseline: baseline.id,
                            metric,
                          })}
                        >
                          并排查看轨迹
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ScoreMatrix
            data={data}
            baseline={baseline.name}
            candidate={candidate.name}
          />
          <details>
            <summary>配置差异（首个共同任务）</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>字段</th>
                    <th>基线</th>
                    <th>当前</th>
                  </tr>
                </thead>
                <tbody>
                  {differences.map((d) => (
                    <tr key={d.field}>
                      <td>{d.field}</td>
                      <td className="break">{d.left}</td>
                      <td className="break">{d.right}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </Panel>
  );
}
