import { useState } from "react";
import { request, useData } from "../api/console";
import { Empty, Notice, Panel } from "../components/common";

interface Artifact {
  artifact_id: string;
  name: string;
  size_bytes: number;
}
function Files({ token, path }: { token: string; path: string }) {
  const files = useData<{ files: { path: string; size_bytes: number }[] }>(
    token,
    path,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState("");
  async function read(member: string, download: boolean) {
    setBusy(true);
    setError("");
    try {
      const data = await request<{ content_base64: string }>(
        token,
        `${path}?member=${encodeURIComponent(member)}`,
      );
      const bytes = Uint8Array.from(atob(data.content_base64), (c) =>
        c.charCodeAt(0),
      );
      if (download) {
        const url = URL.createObjectURL(
          new Blob([bytes], { type: "application/octet-stream" }),
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = member.split("/").pop() || "artifact";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else setPreview(new TextDecoder().decode(bytes));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Notice error={error || files.error} />
      {files.data?.files.map((file) => (
        <div className="section-line" key={file.path}>
          <span className="break">
            {file.path} · {file.size_bytes.toLocaleString()} B
          </span>
          <div className="actions">
            {file.size_bytes <= 256 * 1024 &&
              /\.(json|csv|txt|md|log|yaml|yml)$/i.test(file.path) && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void read(file.path, false)}
                >
                  预览
                </button>
              )}
            <button
              type="button"
              disabled={busy || file.size_bytes > 16 * 1024 ** 2}
              onClick={() => void read(file.path, true)}
            >
              下载
            </button>
          </div>
        </div>
      ))}
      {preview && <pre>{preview}</pre>}
    </>
  );
}
export function ArtifactFiles({
  token,
  path,
}: {
  token: string;
  path: string;
}) {
  const artifacts = useData<{ items: Artifact[] }>(
    token,
    `${path}/artifacts`,
    5000,
  );
  const [selected, setSelected] = useState("");
  return (
    <Panel title="结果文件">
      <Notice error={artifacts.error} />
      <p className="muted">
        仅提供已归档的可见产物；单文件下载上限 16 MiB，文本预览上限 256 KiB。
      </p>
      {artifacts.data?.items.map((item) => (
        <div key={item.artifact_id}>
          <button
            type="button"
            aria-expanded={selected === item.artifact_id}
            onClick={() =>
              setSelected(selected === item.artifact_id ? "" : item.artifact_id)
            }
          >
            {item.name} · {item.size_bytes.toLocaleString()} B
          </button>
          {selected === item.artifact_id && (
            <Files
              key={item.artifact_id}
              token={token}
              path={`${path}/artifacts/${encodeURIComponent(item.artifact_id)}`}
            />
          )}
        </div>
      ))}
      {artifacts.data?.items.length === 0 && (
        <Empty>尚未归档产物，执行结束后刷新。</Empty>
      )}
    </Panel>
  );
}
