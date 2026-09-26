import { useState } from "react";
import { request, useData } from "../../api/console";
import { Empty, Notice } from "../../components/common";

export function EvidenceFiles({
  token,
  path,
}: {
  token: string;
  path: string;
}) {
  const { data, error } = useData<{
    files: { path: string; size_bytes: number }[];
  }>(token, path);
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState<{
    name: string;
    text?: string;
    image?: string;
  }>();
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  async function read(member: string, save: boolean) {
    setBusy(true);
    setFailure("");
    try {
      const value = await request<{ content_base64: string }>(
        token,
        `${path}?member=${encodeURIComponent(member)}`,
      );
      const bytes = Uint8Array.from(atob(value.content_base64), (c) =>
        c.charCodeAt(0),
      );
      if (save) {
        const url = URL.createObjectURL(new Blob([bytes]));
        const a = document.createElement("a");
        a.href = url;
        a.download = member.split("/").pop() ?? "artifact";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else if (/\.(png|jpe?g|webp|gif)$/i.test(member)) {
        const ext = member.split(".").pop()?.toLowerCase();
        setPreview({
          name: member,
          image: `data:image/${ext === "jpg" ? "jpeg" : ext};base64,${value.content_base64}`,
        });
      } else {
        let text = new TextDecoder().decode(bytes);
        if (member.endsWith(".json")) {
          try {
            text = JSON.stringify(JSON.parse(text), null, 2);
          } catch {
            /* Preserve raw content. */
          }
        }
        setPreview({ name: member, text });
      }
    } catch (reason) {
      setFailure(String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <Notice error={failure || error} loading={!data} />
      <label>
        搜索证据文件
        <input
          type="search"
          placeholder="例如：score、stderr、analysis.py"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <div className="bench-file-list">
        {data?.files
          .filter((f) => f.path.toLowerCase().includes(search.toLowerCase()))
          .map((f) => (
            <div className="section-line" key={f.path}>
              <span className="break">
                {f.path}
                <small>{f.size_bytes.toLocaleString()} B</small>
              </span>
              <div className="actions">
                <button
                  type="button"
                  disabled={
                    busy ||
                    f.size_bytes > 1024 ** 2 ||
                    !/\.(jsonl?|csv|txt|md|log|ya?ml|py|sh|toml|png|jpe?g|gif|webp)$/i.test(
                      f.path,
                    )
                  }
                  onClick={() => void read(f.path, false)}
                >
                  预览
                </button>
                <button
                  type="button"
                  disabled={busy || f.size_bytes > 16 * 1024 ** 2}
                  onClick={() => void read(f.path, true)}
                >
                  下载
                </button>
              </div>
            </div>
          ))}
      </div>
      {data?.files.length === 0 && (
        <Empty>尚无归档产物。运行结束并完成采集后可查看。</Empty>
      )}
      {preview && (
        <section className="bench-preview">
          <strong>{preview.name}</strong>
          <button type="button" onClick={() => setPreview(undefined)}>
            关闭预览
          </button>
          {preview.image ? (
            <img src={preview.image} alt={preview.name} />
          ) : (
            <pre>{preview.text}</pre>
          )}
        </section>
      )}
      <small>
        预览上限 1 MiB，下载上限 16 MiB；更大的原始文件可从 Records CLI 导出。
      </small>
    </div>
  );
}
