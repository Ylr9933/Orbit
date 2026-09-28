import { useState } from "react";
import { request } from "../../api/console";
import { taskLabel } from "./presentation";
import type { BatchDetail, ReviewCase } from "./types";
import { download, link, workspace } from "./utils";

export function CaseReview({
  value,
  author,
  batch,
  stale,
  params = {},
}: {
  value: ReviewCase;
  author: string;
  batch: string;
  stale: boolean;
  params?: Record<string, string>;
}) {
  return (
    <section className="result-card research-review">
      <h3>
        研究复盘 <small>解读：{author}</small>
      </h3>
      {stale ? (
        <p className="bench-warning">
          这份复盘对应旧结果，当前运行快照已变化，请重新核对。
        </p>
      ) : (
        <>
          <p>
            <strong>观察：</strong>
            {value.observation}
          </p>
          <p>
            <strong>解释：</strong>
            {value.interpretation}
          </p>
          <p>
            <strong>待验证假设：</strong>
            {value.next}
          </p>
          <div className="actions">
            {value.evidence.map((ref) => (
              <a
                key={`${ref.member}-${ref.step}`}
                href={link({
                  ...params,
                  batch,
                  run: value.run_id,
                  view: ref.member ? "files" : "trace",
                  member: ref.member,
                  step: ref.step,
                  cursor:
                    ref.step == null ? null : Math.floor(ref.step / 50) * 50,
                })}
              >
                {ref.label}
              </a>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export function BatchReview({
  token,
  batch,
  saved,
}: {
  token: string;
  batch: BatchDetail;
  saved: () => void;
}) {
  const review = batch.review;
  const [error, setError] = useState("");
  const [report, setReport] = useState("");
  const [busy, setBusy] = useState(false);
  async function readReport() {
    setError("");
    try {
      const response = await request<{ review: { report: string } | null }>(
        token,
        `${workspace}/${batch.id}/review`,
      );
      setReport(response.review?.report ?? "暂无报告");
    } catch (reason) {
      setError(String(reason));
    }
  }
  return (
    <section className="research-review batch-review">
      {review && (
        <>
          <h3>{review.title}</h3>
          <small>
            研究解读 · {review.author} ·{" "}
            {new Date(review.updated_at).toLocaleDateString()} ·
            假设尚待实验验证
          </small>
          {review.stale ? (
            <p className="bench-warning">
              这份复盘对应旧结果，当前运行快照已变化。旧报告可查阅，摘要不再作为当前结论展示。
            </p>
          ) : (
            <>
              <p>{review.summary}</p>
              <details>
                <summary>{review.cases.length} 个重点案例与证据</summary>
                <div className="review-case-links">
                  {review.cases.map((c) => (
                    <a
                      key={c.run_id}
                      href={link({ batch: batch.id, run: c.run_id })}
                    >
                      {taskLabel(
                        batch.runs.find((r) => r.run_id === c.run_id)
                          ?.unit_id ?? c.run_id,
                      )}
                    </a>
                  ))}
                </div>
              </details>
            </>
          )}
          <div className="actions">
            <button type="button" onClick={() => void readReport()}>
              查看完整复盘报告
            </button>
          </div>
          {report && (
            <details open>
              <summary>完整报告（Markdown 原文）</summary>
              <button
                type="button"
                onClick={() => download("research-review.md", report)}
              >
                下载完整报告
              </button>
              <pre className="review-report">{report}</pre>
            </details>
          )}
        </>
      )}
      <details>
        <summary>{review ? "更新复盘附件" : "导入研究复盘"}</summary>
        <p className="muted">
          上传绑定当前运行快照的 JSON
          复盘附件；不会改动原始评分和提交。记录作者、观察、解释及待验证假设。
        </p>
        <button
          type="button"
          onClick={() =>
            download(
              "review-template.json",
              JSON.stringify(
                {
                  schema_version: 1,
                  snapshot: batch.review_snapshot,
                  title: "研究复盘",
                  author: "",
                  summary: "",
                  report: "",
                  cases: [],
                  revision: review?.revision ?? 0,
                },
                null,
                2,
              ),
            )
          }
        >
          下载当前快照模板
        </button>
        <label>
          选择复盘 JSON
          <input
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setError("");
              setBusy(true);
              try {
                if (file.size > 65536)
                  throw new Error("复盘附件不能超过 64 KiB");
                const value = JSON.parse(await file.text());
                await request(token, `${workspace}/${batch.id}/review`, value);
                setReport("");
                saved();
              } catch (reason) {
                setError(String(reason));
              } finally {
                setBusy(false);
                event.target.value = "";
              }
            }}
          />
        </label>
      </details>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
