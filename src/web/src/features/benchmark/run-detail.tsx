import { useState } from "react";
import { request, useData } from "../../api/console";
import { Notice, Panel } from "../../components/common";
import { EvidenceFiles } from "./evidence-files";
import { Notes } from "./notes";
import { TraceReader } from "./trace-reader";
import type { Annotation, BenchmarkRun } from "./types";
import { duration, link, number, outcome, workspace } from "./utils";

export function RunDetail({
  token,
  batch,
  runId,
  params,
  note = {},
  saved,
  title = "当前实验",
}: {
  token: string;
  batch: string;
  runId: string;
  params: Record<string, string>;
  note?: Annotation;
  saved: () => void;
  title?: string;
}) {
  const path = `${workspace}/${batch}/runs/${runId}`;
  const {
    data: run,
    error,
    refresh,
  } = useData<BenchmarkRun>(token, `${path}/detail`, 5000, finished);
  const [tab, setTab] = useState("auto");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const view =
    tab === "auto" ? (run?.state !== "finished" ? "logs" : "trace") : tab;
  return (
    <Panel title={title}>
      <Notice error={error || failure} loading={!run} />
      {run && (
        <>
          <h3 className="break">{run.unit_id}</h3>
          <div className="bench-run-summary">
            <strong>{outcome(run)}</strong>
            <span>
              {run.model} · {run.agent}
            </span>
            <span>
              耗时 {duration(run.elapsed_seconds)} / 预算{" "}
              {duration(run.budget_seconds)}
            </span>
          </div>
          <div className="bench-score-list">
            {Object.entries(run.metrics).map(([name, value]) => (
              <span key={name}>
                {name} <strong>{number(value)}</strong>
                {!run.score_valid && "（无效评分）"}
              </span>
            ))}
          </div>
          {run.failure_reason && (
            <p className="bench-warning">{run.failure_reason}</p>
          )}
          <small>
            最后活动：{new Date(run.updated_at).toLocaleString()} · 执行{" "}
            {run.execution ?? "进行中"} / 评测 {run.evaluation ?? "未评分"} /
            协议 {run.protocol ?? "未核验"}
          </small>
          {run.state !== "finished" && (
            <p className="muted">
              页面只读取持久状态；队列推进和取消由该批次的 worker
              执行。轨迹与文件在归档后可用。
            </p>
          )}
          <div className="bench-tabs">
            {[
              ["trace", "Agent 轨迹"],
              ["logs", "运行日志"],
              ["files", "文件与评分证据"],
              ["config", "运行配置"],
            ].map(([key, label]) => (
              <button
                type="button"
                key={key}
                aria-pressed={view === key}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {view === "trace" && (
            <TraceReader
              key={`${runId}-${run.has_evidence}`}
              token={token}
              path={`${path}/trajectory`}
              runId={runId}
              locationParams={{ ...params, batch, run: runId }}
              initialCursor={Number(params.cursor ?? 0)}
              focusStep={params.step}
            />
          )}
          {view === "logs" && (
            <RunLog
              token={token}
              path={`${path}/logs`}
              active={run.state !== "finished"}
            />
          )}
          {view === "files" && (
            <EvidenceFiles
              key={`${runId}-${run.has_evidence}`}
              token={token}
              path={`${path}/files`}
            />
          )}
          {view === "config" && (
            <>
              <pre>{JSON.stringify(run.config, null, 2)}</pre>
              <details>
                <summary>资源与清理记录</summary>
                <pre>
                  {JSON.stringify(
                    {
                      resources: run.resources,
                      cleanup_complete: run.cleanup_complete,
                      run_id: run.run_id,
                      attempt_id: run.attempt_id,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      JSON.stringify(run.config, null, 2),
                    );
                    setFailure("");
                  } catch {
                    setFailure("无法复制，请从配置文本中复制");
                  }
                }}
              >
                复制实验配置
              </button>
            </>
          )}
          <Notes
            key={`${batch}-${run.unit_id}`}
            token={token}
            batch={batch}
            unit={run.unit_id}
            initial={run.annotation ?? note}
            saved={saved}
          />
          {run.state !== "finished" && (
            <details>
              <summary>取消此任务</summary>
              <p>请求 worker 取消这个 Run，保留日志与结果，不重新提交任务。</p>
              <button
                type="button"
                disabled={busy || run.cancel_requested}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await request(token, `${path}/cancel`, {});
                    refresh();
                  } catch (reason) {
                    setFailure(String(reason));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                确认请求取消
              </button>
            </details>
          )}
          <small className="break">
            Run {runId} · <a href={link({ batch, run: runId })}>独立详情链接</a>
          </small>
        </>
      )}
    </Panel>
  );
}

function RunLog({
  token,
  path,
  active,
}: {
  token: string;
  path: string;
  active: boolean;
}) {
  const { data, error } = useData<{
    text: string;
    total_bytes: number;
    capture_status: string;
  }>(token, path, active ? 5000 : 0);
  const [follow, setFollow] = useState(true);
  const [snapshot, setSnapshot] = useState("");
  return (
    <>
      <Notice error={error} loading={!data} />
      <div className="section-line">
        <small>
          最近 64 KiB 已采集日志 · {data?.capture_status ?? "读取中"} · 总计{" "}
          {data?.total_bytes ?? 0} 字节
        </small>
        <button
          type="button"
          onClick={() => {
            setSnapshot(data?.text ?? "");
            setFollow(!follow);
          }}
        >
          {follow ? "暂停日志更新" : "继续日志更新"}
        </button>
      </div>
      <pre>
        {(follow ? data?.text : snapshot) ||
          "暂无已采集日志；worker 轮询后会更新。"}
      </pre>
    </>
  );
}

function finished(run: BenchmarkRun) {
  return run.state === "finished";
}
