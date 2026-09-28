import { BatchSummary } from "./batch-summary";
import { BatchHealth } from "./health";
import {
  batchConditions,
  batchState,
  batchTitle,
  metricLabel,
  type ViewParams,
} from "./presentation";
import type { Batch, BatchDetail } from "./types";
import { download, link } from "./utils";

export function BatchHeader({
  selected,
  detail,
  metric,
  metrics,
  params,
  update,
}: {
  selected: Batch;
  detail?: BatchDetail;
  metric: string;
  metrics: string[];
  params: ViewParams;
  update: (values: Record<string, string | null>) => void;
}) {
  const tab = params.tab || "results";
  return (
    <>
      <div className="workbench-heading">
        <div>
          <h2 title={selected.name}>{batchTitle(selected, detail?.runs)}</h2>
          <p className="muted">
            {selected.benchmarks.join(" · ")} · {selected.models.join(" · ")}
            {detail && batchConditions(detail.runs)
              ? ` · ${batchConditions(detail.runs)}`
              : ""}{" "}
            <span className="badge">{batchState(selected)}</span>
          </p>
        </div>
        <div className="actions">
          <a
            className="button-link"
            href={link({ ...params, tab: "comparison" })}
          >
            比较实验
          </a>
          <button
            type="button"
            onClick={() =>
              download(
                "benchmark-experiment.md",
                `# ${selected.name}\n\n${selected.annotation.notes ?? ""}\n\n模型：${selected.models.join(", ")}\n\n数值评分 ${selected.scored}/${selected.total}\n\n${metric}：${selected.metrics[metric]?.mean ?? "—"}（本地描述性均值，非官方总分）\n\n评分需复核：${selected.health?.needs_review ?? "未知"}；健康未知：${selected.health?.unknown ?? "未知"}；求解异常：${selected.health?.solver_failed ?? "未知"}。均分保留异常评分，不能据此直接推断能力。\n`,
              )
            }
          >
            导出实验摘要
          </button>
        </div>
      </div>
      {detail && (
        <BatchSummary
          batch={detail}
          metric={metric}
          showZero={() =>
            update({ filter: "zero", page: null, tab: "results" })
          }
        />
      )}
      <BatchHealth
        batch={selected.id}
        health={detail?.health ?? selected.health}
      />
      <div className="workbench-tab-row">
        <nav className="workbench-tabs" aria-label="实验详情">
          <a
            aria-current={tab === "results" ? "page" : undefined}
            href={link({ ...params, tab: "results" })}
          >
            任务结果
          </a>
          <a
            aria-current={tab === "distribution" ? "page" : undefined}
            href={link({ ...params, tab: "distribution" })}
          >
            得分分布
          </a>
          <a
            aria-current={tab === "comparison" ? "page" : undefined}
            href={link({ ...params, tab: "comparison" })}
          >
            实验比较
          </a>
          <a
            aria-current={tab === "notes" ? "page" : undefined}
            href={link({ ...params, tab: "notes" })}
          >
            实验笔记
          </a>
        </nav>
        {metrics.length > 1 && (
          <label className="inline">
            评分指标
            <select
              value={metric}
              onChange={(e) => update({ metric: e.target.value })}
            >
              {metrics.map((m) => (
                <option key={m} value={m}>
                  {metricLabel(m)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
    </>
  );
}
