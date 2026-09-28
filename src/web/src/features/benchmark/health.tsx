import type { BenchmarkRun, HealthSummary } from "./types";
import { link } from "./utils";

export const solverLabel = (run: BenchmarkRun) =>
  ({
    completed: "正常结束（终止事件）",
    failed: "异常结束（终止事件）",
    quota_exhausted: "额度耗尽中断",
    unknown: "未确认终止事件",
  })[run.health?.solver.status ?? "unknown"];

export function BatchHealth({
  health,
  batch,
}: {
  health?: HealthSummary;
  batch: string;
}) {
  if (!health) return null;
  return (
    <div className="health-summary">
      <div className="actions">
        <a href={link({ batch, filter: "evaluation" })}>
          {health.needs_review} 题评分需要复核
        </a>
        <a href={link({ batch, filter: "solver" })}>
          {health.solver_failed} 题求解异常结束
        </a>
        {health.status_conflicts > 0 && (
          <a href={link({ batch, filter: "conflict" })}>
            {health.status_conflicts} 题状态记录有冲突
          </a>
        )}
      </div>
      <small>
        {health.needs_review > 0
          ? "当前均分包含评分异常，暂不宜直接用于能力比较。"
          : "自动检查未发现异常不等于科学结论已通过验证。"}
        {health.unknown > 0 &&
          ` ${health.unknown} 题评分健康尚未检查或证据不足。`}
        分数保持原值。
      </small>
    </div>
  );
}

export function RunHealthView({
  run,
  batch,
  params = {},
}: {
  run: BenchmarkRun;
  batch: string;
  params?: Record<string, string>;
}) {
  const health = run.health;
  const status = health?.evaluation.status ?? "unknown";
  const kinds = new Set(health?.evaluation.issues.map((i) => i.kind));
  return (
    <section className="result-card">
      <h3>证据核验</h3>
      <p>
        {status === "needs_review"
          ? "评分需要复核"
          : status === "unknown"
            ? "评分健康未知"
            : "自动检查未发现已知评分异常"}
      </p>
      {kinds.has("judge_unavailable") && <p>评分分项记录了 judge 不可用。</p>}
      {kinds.has("missing_dependency") && (
        <p>评分分项记录了输入文件或运行依赖缺失。</p>
      )}
      {health?.evaluation.hard_gates_passed === false && (
        <p>硬性检查未通过，请结合分项原因判断。</p>
      )}
      <p>Agent：{solverLabel(run)}</p>
      {health?.solver.status_conflict && (
        <p className="bench-warning">
          原生状态 {health.solver.native_status}{" "}
          与终止事件不一致；两者分别保留。
        </p>
      )}
      <small>
        来自归档证据的自动检查，与人工或 Codex
        的研究解读分开。未命中规则不代表评分无误。
      </small>
      <div className="actions">
        {run.has_evidence && health && (
          <>
            <a
              href={link({
                ...params,
                batch,
                run: run.run_id,
                view: "files",
                member: health.evaluation.member,
              })}
            >
              评分原始证据
            </a>
            <a
              href={link({
                ...params,
                batch,
                run: run.run_id,
                view: "files",
                member: health.solver.member,
              })}
            >
              Agent 终止证据
            </a>
          </>
        )}
      </div>
      {!!health?.evaluation.issues.length && (
        <details>
          <summary>异常所在分项</summary>
          <ul>
            {health.evaluation.issues.map((issue) => (
              <li key={`${issue.kind}-${issue.path}`}>
                <code>{issue.path}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
