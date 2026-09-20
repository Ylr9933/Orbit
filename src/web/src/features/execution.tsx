import { useState } from "react";
import {
  known,
  pretty,
  request,
  type TraceEvent,
  useData,
} from "../api/console";
import type { Capabilities, ControlRun } from "../api/workflow";
import { Badge, Empty, Notice, Panel } from "../components/common";
import { ArtifactFiles } from "./execution-artifacts";

export function ExecutionList({ runs }: { runs: ControlRun[] }) {
  return runs.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>状态</th>
            <th>执行结果</th>
            <th>创建时间</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <a href={`#execution/${encodeURIComponent(run.run_id)}`}>
                  {run.run_id} ↗
                </a>
              </td>
              <td>
                {run.state}
                {run.cancel_requested
                  ? run.state === "finished"
                    ? " · 已处理取消请求"
                    : " · 已请求取消"
                  : ""}
              </td>
              <td>
                {run.result?.execution_status ?? run.result?.status ?? "—"}
              </td>
              <td>{new Date(run.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty>
      还没有科研运行。从已采用的实验提交，或通过宿主机 Agent 开始科研。
    </Empty>
  );
}
export function ExecutionRecent({ token }: { token: string }) {
  const capabilities = useData<Capabilities>(token, "capabilities");
  const [offset, setOffset] = useState(0);
  const runs = useData<{ items: ControlRun[]; next_offset: number | null }>(
    token,
    capabilities.data?.project_workspaces
      ? `execution/runs?offset=${offset}`
      : null,
    5000,
  );
  if (!capabilities.data?.project_workspaces) return null;
  return (
    <Panel title="科研工作流运行">
      <Notice error={runs.error} />
      <ExecutionList runs={runs.data?.items ?? []} />
      <div className="actions">
        <button
          type="button"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          前 100 次
        </button>
        <button
          type="button"
          disabled={runs.data?.next_offset == null}
          onClick={() => setOffset(runs.data?.next_offset ?? 0)}
        >
          后 100 次
        </button>
      </div>
    </Panel>
  );
}
function Events({ token, path }: { token: string; path: string }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const events = useData<{ items: TraceEvent[]; next_cursor: string | null }>(
    token,
    `${path}/events${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    5000,
  );
  return (
    <Panel title="执行轨迹">
      <p className="muted">
        每 5 秒读取已持久化事件；不代表实时模型流，私有事件不展示。
      </p>
      <Notice error={events.error} />
      {events.data?.items.map((e) => (
        <article className="event" key={e.id}>
          <strong>{e.type}</strong>
          <small>
            {" "}
            · {e.at} · {e.capture_status}
          </small>
          {e.text && <pre>{e.text}</pre>}
          <details>
            <summary>事件字段</summary>
            <pre>{pretty(e.payload)}</pre>
          </details>
        </article>
      ))}
      {events.data?.items.length === 0 && <Empty>本页尚无可见事件。</Empty>}
      <div className="actions">
        <button
          type="button"
          disabled={!cursor}
          onClick={() => setCursor(null)}
        >
          回到开始
        </button>
        <button
          type="button"
          disabled={!events.data?.next_cursor}
          onClick={() => setCursor(events.data?.next_cursor ?? null)}
        >
          下一页事件
        </button>
      </div>
    </Panel>
  );
}
export function ExecutionDetail({ token, id }: { token: string; id: string }) {
  const path = `execution/runs/${encodeURIComponent(id)}`;
  const run = useData<ControlRun>(token, path, 5000);
  const capabilities = useData<Capabilities>(token, "capabilities", 10000);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const value = run.data;
  return (
    <>
      <div className="section-line">
        <h2 className="break">{id}</h2>
        <a href="#runs">← 全部运行</a>
      </div>
      <Notice error={run.error || error} loading={!value} />
      {value && (
        <>
          <Panel title="运行状态">
            <Badge>Run：{value.state}</Badge>
            <p>
              执行结果：
              {value.result?.execution_status ??
                value.result?.status ??
                "进行中 / 待执行"}
            </p>
            <p>
              评测：{value.result?.evaluation_status ?? "未记录"} · 归档：
              {value.result?.archive_status ?? "未记录"}
            </p>
            <p>
              清理完成：{known(value.result?.cleanup_complete)} · 租约释放：
              {known(value.result?.lease_released)}
            </p>
            <p>类型：{value.kind}</p>
            {value.lineage.project_id && (
              <a href={`#projects/${value.lineage.project_id}`}>查看所属项目</a>
            )}
            {value.kind === "experiment" &&
              ["accepted", "running"].includes(value.state) && (
                <div className="actions">
                  <button
                    type="button"
                    disabled={
                      busy ||
                      value.cancel_requested ||
                      !capabilities.data?.run_control
                    }
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        await request(token, `${path}/cancel`, {});
                        run.refresh();
                      } catch (reason) {
                        setError(String(reason));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {value.cancel_requested
                      ? "正在取消，等待清理…"
                      : "取消运行"}
                  </button>
                </div>
              )}
            {value.kind !== "experiment" &&
              !["finished", "quarantined"].includes(value.state) && (
                <p className="muted">
                  长期环境 / Planner 请通过 research close、environment cancel
                  或 planner stop 结束。
                </p>
              )}
            {!capabilities.data?.run_control && (
              <p>{capabilities.data?.controller_reason}</p>
            )}
          </Panel>
          {Boolean(value.jobs?.length) && (
            <Panel title="容器内 Job">
              {value.jobs?.map((job) => (
                <p key={job.job_id}>
                  {job.job_id} · Job：{job.state} · exit code：
                  {job.exit_code ?? "—"}
                </p>
              ))}
            </Panel>
          )}
          <ArtifactFiles token={token} path={path} />
          <Events token={token} path={path} />
        </>
      )}
    </>
  );
}
