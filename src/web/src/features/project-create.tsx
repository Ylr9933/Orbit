import { useState } from "react";
import { request } from "../api/console";
import { finishOperation, operationId } from "../api/operations";
import { Notice, Panel } from "../components/common";

export function ProjectCreate({
  token,
  close,
}: {
  token: string;
  close: () => void;
}) {
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [directory, setDirectory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Panel title="新建科研工作区">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          const body = { name, goal, directory };
          try {
            const saved = await request<{ project_id: string }>(
              token,
              "projects/init",
              {
                ...body,
                operation_id: operationId("init", body),
              },
            );
            finishOperation("init");
            location.hash = `projects/${saved.project_id}`;
            close();
          } catch (reason) {
            setError(String(reason));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          项目名称
          <input
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          研究目标
          <textarea
            required
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <label>
          服务器工作区路径
          <input
            required
            placeholder="/research/position-encoding"
            value={directory}
            onChange={(e) => setDirectory(e.target.value)}
          />
        </label>
        <p className="muted">
          使用与 CLI 相同的初始化服务，创建 docs、code、data、runs
          等目录。请输入绝对路径，父目录需已存在；不会覆盖已有目录。
        </p>
        <Notice error={error} />
        <div className="actions">
          <button className="primary" disabled={busy} type="submit">
            {busy ? "创建中…" : "创建工作区"}
          </button>
          <button disabled={busy} type="button" onClick={close}>
            取消
          </button>
        </div>
      </form>
    </Panel>
  );
}
