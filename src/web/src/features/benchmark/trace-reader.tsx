import { useEffect, useState } from "react";
import { useData } from "../../api/console";
import { Empty, Notice } from "../../components/common";
import type { Step, Trajectory } from "./types";
import { groupSteps, isError, link } from "./utils";

const stepLabels: Record<string, string> = {
  llm_response: "Agent 消息",
  agent_message: "Agent 消息",
  user_message: "用户消息",
  command_execution: "执行命令",
  tool_call: "工具调用",
  tool_result: "工具返回",
  file_change: "文件修改",
  reasoning: "已记录的思考",
  llm_request: "模型请求",
};
const captureLabels: Record<string, string> = {
  complete: "完整",
  partial: "部分采集",
  truncated: "有截断",
  unavailable: "不可用",
  missing: "缺失",
};
function StepContent({ step }: { step: Step }) {
  return (
    <>
      {["llm_response", "agent_message", "user_message"].includes(
        step.step_type,
      ) ? (
        <div className="trace-message">{step.content}</div>
      ) : (
        <pre>{step.content}</pre>
      )}
      {step.content_truncated && (
        <small>此步骤显示前 64 KiB，完整内容见原始证据。</small>
      )}
    </>
  );
}

export function TraceReader({
  token,
  path,
  runId,
  locationParams,
  initialCursor = 0,
  focusStep,
}: {
  token: string;
  path: string;
  runId: string;
  locationParams: Record<string, string>;
  initialCursor?: number;
  focusStep?: string;
}) {
  const [search, setSearch] = useState(locationParams.traceSearch ?? "");
  const [query, setQuery] = useState(locationParams.traceSearch ?? "");
  const [kind, setKind] = useState(locationParams.traceKind ?? "all");
  const [cursor, setCursor] = useState(initialCursor);
  const [copied, setCopied] = useState("");
  const params = new URLSearchParams({
    cursor: String(cursor),
    limit: "50",
    search: query,
    kind,
  });
  const { data, error } = useData<Trajectory>(token, `${path}?${params}`);
  useEffect(() => {
    if (search === query) return;
    const timer = setTimeout(() => {
      setQuery(search);
      setCursor(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [search, query]);
  useEffect(() => {
    if (data && focusStep)
      document
        .getElementById(`step-${runId}-${focusStep}`)
        ?.scrollIntoView({ block: "center" });
  }, [data, focusStep, runId]);
  const groups = groupSteps(data?.steps ?? []);
  return (
    <>
      <div className="bench-filters">
        <label>
          搜索轨迹
          <input
            type="search"
            placeholder="命令、错误或输出内容"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          步骤类型
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setCursor(0);
            }}
          >
            <option value="all">全部步骤</option>
            <option value="errors">错误</option>
            <option value="tools">工具调用</option>
            <option value="agent">Agent 消息</option>
          </select>
        </label>
      </div>
      <div className="actions">
        <button
          type="button"
          onClick={() => {
            setKind("errors");
            setSearch("");
            setCursor(0);
          }}
        >
          定位错误
        </button>
        <button
          type="button"
          disabled={!data?.matched_steps}
          onClick={() =>
            setCursor(Math.floor(((data?.matched_steps ?? 1) - 1) / 50) * 50)
          }
        >
          最后一页
        </button>
        {copied && <small role="status">{copied}</small>}
      </div>
      <Notice error={error} loading={!data} />
      {data && (
        <>
          {data.calls.last_reported_usage && (
            <details>
              <summary>已采集的模型用量</summary>
              <dl className="readable-config">
                {Object.entries(data.calls.last_reported_usage).map(
                  ([name, value]) => (
                    <div key={name}>
                      <dt>{name}</dt>
                      <dd>{value.toLocaleString()}</dd>
                    </div>
                  ),
                )}
              </dl>
              <small>上游最近报告的用量，不推算费用。</small>
            </details>
          )}
          <small>
            匹配 {data.matched_steps} 步 · 采集{" "}
            {captureLabels[data.trajectory.capture_status] ??
              data.trajectory.capture_status}{" "}
            · {data.trajectory.origin ?? "原生轨迹"}
          </small>
          {["truncated", "partial", "missing"].includes(
            data.trajectory.capture_status,
          ) && (
            <p className="bench-warning">
              轨迹采集不完整或存在截断。搜索仅覆盖已归档内容；可在文件页查看原始证据。
            </p>
          )}
          {groups.length === 0 && (
            <Empty>
              {query || kind !== "all"
                ? "没有匹配的步骤。"
                : "轨迹尚未归档或该运行没有可用的 Agent 轨迹。"}
            </Empty>
          )}
          <section className="bench-steps" aria-label="归档轨迹步骤">
            {groups.map(({ step, response }) => (
              <article
                className={`bench-step ${isError(step) || (response && isError(response)) ? "bench-step-error" : ""}`}
                id={`step-${runId}-${step.step_index}`}
                key={step.step_index}
              >
                <div className="section-line">
                  <strong>
                    #{step.step_index} ·{" "}
                    {step.metadata.tool_name ??
                      step.metadata.parent_tool_name ??
                      stepLabels[step.step_type] ??
                      step.step_type}
                  </strong>
                  <button
                    type="button"
                    onClick={async () => {
                      const hash = link({
                        ...locationParams,
                        cursor,
                        view: "trace",
                        traceSearch: query,
                        traceKind: kind,
                        step: step.step_index,
                      });
                      try {
                        await navigator.clipboard.writeText(
                          `${location.origin}${location.pathname}${hash}`,
                        );
                        setCopied(`已复制步骤 #${step.step_index} 链接`);
                      } catch {
                        setCopied("复制失败，可从浏览器地址栏复制");
                      }
                    }}
                  >
                    复制步骤链接
                  </button>
                </div>
                <small>
                  {step.timestamp_ms != null
                    ? new Date(step.timestamp_ms).toLocaleTimeString()
                    : ""}
                  {step.metadata.exit_code != null
                    ? ` · 退出码 ${step.metadata.exit_code}`
                    : ""}
                  {step.metadata.duration_ms != null
                    ? ` · ${step.metadata.duration_ms} ms`
                    : ""}
                </small>
                {step.content.length > 800 ? (
                  <details open={isError(step)}>
                    <summary>{step.content.slice(0, 160)}…</summary>
                    <StepContent step={step} />
                  </details>
                ) : (
                  <StepContent step={step} />
                )}
                {response && (
                  <details open={isError(response)}>
                    <summary>
                      返回结果
                      {response.metadata.exit_code != null
                        ? ` · 退出码 ${response.metadata.exit_code}`
                        : ""}
                    </summary>
                    <StepContent step={response} />
                  </details>
                )}
              </article>
            ))}
          </section>
          <div className="actions">
            <button
              type="button"
              disabled={cursor === 0}
              onClick={() => setCursor(Math.max(0, cursor - 50))}
            >
              上一页轨迹
            </button>
            <span>
              {data.matched_steps ? cursor + 1 : 0}–
              {cursor + (data.steps.length ?? 0)} / {data.matched_steps}
            </span>
            <button
              type="button"
              disabled={data.next_cursor == null}
              onClick={() => setCursor(data.next_cursor ?? 0)}
            >
              下一页轨迹
            </button>
          </div>
        </>
      )}
    </>
  );
}
