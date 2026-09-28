import { useState } from "react";
import { solverLabel } from "./health";
import { configFields, metricLabel, taskTimeout } from "./presentation";
import type { BenchmarkRun } from "./types";
import { duration, number, outcome } from "./utils";

export function RunResult({
  run,
  files,
  trace,
}: {
  run: BenchmarkRun;
  files: () => void;
  trace: () => void;
}) {
  return (
    <div className="run-result-grid">
      <section className="result-card">
        <h3>评分结果</h3>
        {Object.keys(run.metrics).length ? (
          Object.entries(run.metrics).map(([key, value]) => (
            <div key={key} className="result-score">
              <span>{metricLabel(key)}</span>
              <strong>{run.score_valid ? number(value) : "—"}</strong>
              {!run.score_valid && (
                <small>原生值 {number(value)}，未通过评分有效性检查</small>
              )}
            </div>
          ))
        ) : (
          <p>尚无有效评分。</p>
        )}
        <span className="badge">{outcome(run)}</span>
        <p className="muted">
          {run.score_valid
            ? "已保存数值评分，零分照常保留；评分健康与 Agent 结束情况请看下方证据核验。"
            : "需要先检查运行状态和诊断信息；未评分不会计为零分。"}
        </p>
        <div className="actions">
          <button type="button" disabled={!run.has_evidence} onClick={files}>
            查看评分与提交文件
          </button>
          <button type="button" disabled={!run.has_evidence} onClick={trace}>
            阅读 Agent 轨迹
          </button>
        </div>
      </section>
      <section className="result-card">
        <h3>执行概况</h3>
        <dl>
          <dt>运行耗时</dt>
          <dd>{duration(run.elapsed_seconds)}</dd>
          <dt>求解时限</dt>
          <dd>
            {taskTimeout(run) == null
              ? "未单独记录"
              : duration(taskTimeout(run))}
          </dd>
          <dt>Agent 结束</dt>
          <dd>{solverLabel(run)}</dd>
          <dt>Infra 执行记录</dt>
          <dd>
            {(
              {
                completed: "已完成",
                failed: "失败",
                timed_out: "超时",
                cancelled: "已取消",
              } as Record<string, string>
            )[run.execution ?? ""] ??
              run.execution ??
              "尚未结束"}
          </dd>
          <dt>评测状态</dt>
          <dd>
            {(
              {
                scored: "已评分",
                failed: "评分失败",
                skipped: "未评测",
              } as Record<string, string>
            )[run.evaluation ?? ""] ??
              run.evaluation ??
              "未评分"}
          </dd>
          <dt>协议核验</dt>
          <dd>
            {run.protocol === "valid"
              ? "有效"
              : run.protocol === "invalid"
                ? "无效"
                : (run.protocol ?? "未核验")}
          </dd>
          <dt>证据归档</dt>
          <dd>{run.has_evidence ? "已有归档" : "尚未归档"}</dd>
          <dt>资源清理</dt>
          <dd>
            {run.cleanup_complete === true
              ? "已完成"
              : run.cleanup_complete === false
                ? "未完成"
                : "未记录"}
          </dd>
        </dl>
        {run.cleanup_complete === false && (
          <p className="bench-warning">清理尚未完成，请检查资源状态。</p>
        )}
      </section>
    </div>
  );
}
export function RunConfig({ run }: { run: BenchmarkRun }) {
  const [message, setMessage] = useState("");
  return (
    <>
      <dl className="readable-config">
        {configFields(run).map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">资源为请求配置；实际分配与使用量见下方记录。</p>
      <details>
        <summary>完整配置、资源与技术信息</summary>
        <pre>
          {JSON.stringify(
            {
              config: run.config,
              resources: run.resources,
              run_id: run.run_id,
              attempt_id: run.attempt_id,
              outer_budget_seconds: run.budget_seconds,
              cleanup_complete: run.cleanup_complete,
            },
            null,
            2,
          )}
        </pre>
        <small>
          外层预算 {duration(run.budget_seconds)}
          ，可能包含准备、求解和归档开销，不代表实际耗时。
        </small>
      </details>
      <div className="actions">
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                JSON.stringify(run.config, null, 2),
              );
              setMessage("配置已复制");
            } catch {
              setMessage("复制失败，请展开完整配置手动复制。");
            }
          }}
        >
          复制实验配置
        </button>
        <span role="status">{message}</span>
      </div>
    </>
  );
}
