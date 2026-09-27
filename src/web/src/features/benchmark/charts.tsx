import { useRef } from "react";
import type { Batch, Comparison } from "./types";
import { download, link, number } from "./utils";

export function Trend({
  batches,
  selected,
  metric,
}: {
  batches: Batch[];
  selected: Batch;
  metric: string;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const points = batches
    .filter(
      (b) =>
        !b.duplicate_tasks &&
        b.cohort === selected.cohort &&
        b.total > 0 &&
        b.metrics[metric]?.count === b.total,
    )
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const values = points.map((p) => p.metrics[metric].mean);
  const min = Math.min(...values),
    max = Math.max(...values);
  const x = (i: number) => 70 + (i * 590) / Math.max(points.length - 1, 1);
  const y = (v: number) => 155 - ((v - min) / (max - min || 1)) * 110;
  return (
    <section className="bench-chart">
      <div className="section-line">
        <h3>实验得分趋势</h3>
        <button
          type="button"
          disabled={!points.length}
          onClick={() =>
            svg.current &&
            download(
              "benchmark-trend.svg",
              svg.current.outerHTML,
              "image/svg+xml",
            )
          }
        >
          导出图表
        </button>
      </div>
      <p className="muted">
        同任务集、同材料与评分版本，全部任务具有有效评分时纳入。纵轴为{" "}
        {metric || "所选指标"} 的描述性均值。
      </p>
      {points.length ? (
        <svg
          ref={svg}
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 720 210"
          role="img"
          aria-label="完整批次得分趋势"
          style={{ background: "white", color: "#203b3b" }}
        >
          <title>完整批次描述性均值；不是官方总分</title>
          <line x1="60" x2="680" y1="165" y2="165" stroke="#bacdca" />
          <text x="8" y="48" fontSize="12" fill="currentColor">
            {number(max)}
          </text>
          <text x="8" y="159" fontSize="12" fill="currentColor">
            {number(min)}
          </text>
          {points.length > 1 && (
            <polyline
              fill="none"
              stroke="#087d70"
              strokeWidth="2"
              points={points
                .map((p, i) => `${x(i)},${y(p.metrics[metric].mean)}`)
                .join(" ")}
            />
          )}
          {points.map((p, i) => (
            <a
              key={p.id}
              href={link({ batch: p.id, metric })}
              aria-label={`${p.name}，均值 ${number(p.metrics[metric].mean)}`}
            >
              <circle
                cx={x(i)}
                cy={y(p.metrics[metric].mean)}
                r={p.id === selected.id ? 7 : 5}
                fill="#087d70"
              >
                <title>
                  {p.name}: {number(p.metrics[metric].mean)}
                </title>
              </circle>
              <text
                x={x(i)}
                y="190"
                textAnchor="middle"
                fontSize="11"
                fill="currentColor"
              >
                {i + 1}
              </text>
            </a>
          ))}
        </svg>
      ) : (
        <p className="empty">
          还没有同任务集的完整评分批次。可先查看下方逐题结果。
        </p>
      )}
      <div className="bench-legend">
        {points.map((p, i) => (
          <a key={p.id} href={link({ batch: p.id, metric })}>
            {i + 1}. {p.name}
          </a>
        ))}
      </div>
    </section>
  );
}

export function ScoreMatrix({
  data,
  baseline,
  candidate,
}: {
  data: Comparison;
  baseline: string;
  candidate: string;
}) {
  return (
    <details>
      <summary>任务得分矩阵</summary>
      <div className="bench-matrix">
        <span>任务</span>
        <strong>{baseline}</strong>
        <strong>{candidate}</strong>
        {data.rows.map((row) => (
          <div className="bench-matrix-row" key={row.unit_id}>
            <span>{row.unit_id}</span>
            {[row.left, row.right].map((run, index) => {
              const value = run?.score_valid ? run.metrics[data.metric] : null;
              return (
                <span
                  key={index === 0 ? "baseline" : "candidate"}
                  className={
                    value == null
                      ? "score-missing"
                      : value === 0
                        ? "score-zero"
                        : "score-present"
                  }
                >
                  {number(value)}
                </span>
              );
            })}
          </div>
        ))}
      </div>
      <small>颜色区分有效分数、零分与缺失；不同指标不统一缩放。</small>
    </details>
  );
}
