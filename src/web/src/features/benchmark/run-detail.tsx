import { useEffect, useState } from "react";
import { request, useData } from "../../api/console";
import { Notice, Panel } from "../../components/common";
import { EvidenceFiles } from "./evidence-files";
import { RunHealthView } from "./health";
import { Notes } from "./notes";
import { taskLabel } from "./presentation";
import { CaseReview } from "./review";
import { RunConfig, RunResult } from "./run-result";
import { TraceReader } from "./trace-reader";
import type { Annotation, BenchmarkRun } from "./types";
import { link, outcome, workspace } from "./utils";

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
  const [tab, setTab] = useState(
    params.view ?? (params.step ? "trace" : "auto"),
  );
  useEffect(() => {
    setTab(params.view ?? (params.step ? "trace" : "auto"));
  }, [params.view, params.step]);
  const selectTab = (value: string) => {
    setTab(value);
    if (title !== "基线实验") {
      history.replaceState(
        null,
        "",
        `${location.pathname}${location.search}${link({ ...params, view: value, step: null, cursor: null })}`,
      );
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  };
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const [evidenceRevision, setEvidenceRevision] = useState(0);
  const view =
    tab === "auto" ? (run?.state !== "finished" ? "logs" : "result") : tab;
  return (
    <Panel title={title}>
      <Notice error={error || failure} loading={!run} />
      {run && (
        <>
          <div className="section-line">
            <h3 className="task-title" title={run.unit_id}>
              {taskLabel(run.unit_id)}
            </h3>
            <button
              type="button"
              onClick={() => {
                refresh();
                setEvidenceRevision((n) => n + 1);
              }}
            >
              刷新任务
            </button>
          </div>
          <div className="bench-run-summary">
            <span className="badge">{outcome(run)}</span>
            <span>
              {run.model} · {run.agent}
            </span>
            <small>最后活动：{new Date(run.updated_at).toLocaleString()}</small>
          </div>
          {run.failure_reason && (
            <p className="bench-warning">{run.failure_reason}</p>
          )}
          {run.state !== "finished" && (
            <p className="muted">
              页面只读取持久状态；队列推进和取消由该批次的 worker
              执行。轨迹与文件在归档后可用。
            </p>
          )}
          <div className="bench-tabs">
            {[
              ["result", "结果"],
              ["trace", "Agent 轨迹"],
              ["logs", "运行日志"],
              ["files", "文件与评分证据"],
              ["config", "运行配置"],
            ].map(([key, label]) => (
              <button
                type="button"
                key={key}
                aria-pressed={view === key}
                onClick={() => selectTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {view === "result" && (
            <RunResult
              run={run}
              files={() => selectTab("files")}
              trace={() => selectTab("trace")}
            />
          )}
          {view === "result" && (
            <>
              <RunHealthView run={run} batch={batch} params={params} />
              {run.review?.case && (
                <CaseReview
                  value={run.review.case}
                  author={run.review.author}
                  batch={batch}
                  stale={run.review.stale}
                  params={params}
                />
              )}
            </>
          )}
          {view === "trace" && (
            <TraceReader
              key={`${runId}-${run.has_evidence}-${evidenceRevision}`}
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
              key={evidenceRevision}
              token={token}
              path={`${path}/logs`}
              active={run.state !== "finished"}
            />
          )}
          {view === "files" && (
            <EvidenceFiles
              key={`${runId}-${run.has_evidence}-${evidenceRevision}-${params.member}`}
              token={token}
              path={`${path}/files`}
              initialMember={params.member}
            />
          )}
          {view === "config" && <RunConfig run={run} />}
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
          <details>
            <summary>任务标识与链接</summary>
            <p className="break">{run.unit_id}</p>
            <small className="break">
              Run {runId} ·{" "}
              <a href={link({ batch, run: runId, view })}>独立详情链接</a>
            </small>
          </details>
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
