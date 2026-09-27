import { useState } from "react";
import { request } from "../../api/console";
import { Notice } from "../../components/common";
import type { Annotation } from "./types";
import { workspace } from "./utils";

export function Notes({
  token,
  batch,
  unit,
  initial,
  saved,
}: {
  token: string;
  batch: string;
  unit?: string;
  initial: Annotation;
  saved: () => void;
}) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return (
    <details className="bench-notes">
      <summary>
        {unit ? "任务笔记" : "实验名称、说明与标签"}
        {value.notes ? " · 已有记录" : ""}
      </summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const result = await request<Annotation>(
              token,
              `${workspace}/${batch}/note${unit ? `?unit=${encodeURIComponent(unit)}` : ""}`,
              value,
            );
            setValue(result);
            setMessage("已保存");
            saved();
          } catch (reason) {
            setError(String(reason));
          } finally {
            setBusy(false);
          }
        }}
      >
        {!unit && (
          <div className="bench-filters">
            <label>
              实验名称
              <input
                maxLength={120}
                value={value.name ?? ""}
                onChange={(e) => setValue({ ...value, name: e.target.value })}
              />
            </label>
            <label>
              关联研究项目
              <input
                maxLength={200}
                placeholder="项目名称或标识"
                value={value.project ?? ""}
                onChange={(e) =>
                  setValue({ ...value, project: e.target.value })
                }
              />
            </label>
            <label>
              标签
              <input
                maxLength={500}
                placeholder="例如：baseline, 提示词改进"
                value={value.tags ?? ""}
                onChange={(e) => setValue({ ...value, tags: e.target.value })}
              />
            </label>
          </div>
        )}
        <label>
          实验笔记
          <textarea
            rows={4}
            maxLength={12000}
            placeholder="这次改了什么？结果说明什么？下一步验证什么？"
            value={value.notes ?? ""}
            onChange={(e) => {
              setMessage("");
              setValue({ ...value, notes: e.target.value });
            }}
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "保存中…" : "保存笔记"}
          </button>
          <span role="status">{message}</span>
        </div>
        <Notice error={error} />
      </form>
    </details>
  );
}
