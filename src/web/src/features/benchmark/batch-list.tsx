import { useState } from "react";
import { request } from "../../api/console";
import { Empty, Notice } from "../../components/common";
import { BatchNotifications } from "./notifications";
import { batchState, metricLabel } from "./presentation";
import type { Batch } from "./types";
import { link, number, workspace } from "./utils";

export function BatchList({
  token,
  batches,
  baseline,
  refresh,
}: {
  token: string;
  batches: Batch[];
  baseline: string;
  refresh: () => void;
}) {
  const [search, setSearch] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows = batches
    .filter((b) =>
      `${b.name} ${b.models} ${b.benchmarks} ${b.annotation.tags ?? ""} ${b.annotation.project ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(b.finished < b.total) - Number(a.finished < a.total) ||
        b.updated_at.localeCompare(a.updated_at),
    );
  return (
    <>
      <div className="workbench-heading">
        <div>
          <h2>实验</h2>
          <p className="muted">查看结果，比较改动，回到每一次执行。</p>
        </div>
        <a href="#projects">进入科研项目 →</a>
      </div>
      <div className="list-toolbar">
        <label>
          搜索实验
          <input
            type="search"
            placeholder="名称、模型、标签或研究项目"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <span className="muted">{rows.length} 个实验</span>
      </div>
      {!batches.length ? (
        <Empty>
          还没有实验记录。登记已有批次查看评测结果，或进入科研项目创建研究工作区。
        </Empty>
      ) : rows.length ? (
        <div className="table-wrap workbench-table">
          <table>
            <thead>
              <tr>
                <th>实验</th>
                <th>模型</th>
                <th className="numeric">平均分</th>
                <th>数值评分</th>
                <th>状态</th>
                <th>最近活动</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => {
                const metric = Object.keys(b.metrics)[0];
                return (
                  <tr key={b.id}>
                    <th scope="row">
                      <a href={link({ batch: b.id })}>{b.name}</a>
                      {b.id === baseline && <span className="badge">基线</span>}
                      <small>
                        {b.benchmarks.join(" · ")}
                        {b.annotation.project
                          ? ` · ${b.annotation.project}`
                          : ""}
                      </small>
                    </th>
                    <td>{b.models.join(" · ") || "未记录"}</td>
                    <td className="numeric">
                      {number(b.metrics[metric]?.mean)}
                      <small>{metricLabel(metric)}</small>
                      {!!b.health?.needs_review && (
                        <small>{b.health.needs_review} 题评分需复核</small>
                      )}
                    </td>
                    <td>
                      {b.scored} / {b.total}
                    </td>
                    <td>
                      <span className="badge">{batchState(b)}</span>
                      {b.finished < b.total && (
                        <progress
                          aria-label={`${b.name} 完成进度`}
                          value={b.finished}
                          max={b.total || 1}
                        />
                      )}
                    </td>
                    <td className="muted">
                      {b.updated_at
                        ? new Date(b.updated_at).toLocaleString()
                        : "尚未提交"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>
          没有匹配的实验。
          <button type="button" onClick={() => setSearch("")}>
            清除搜索
          </button>
        </Empty>
      )}
      <details className="bench-register" open={!batches.length}>
        <summary>登记已有批次</summary>
        <p className="muted">
          选择服务器上的批次目录，添加到工作台供查看与比较。
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const value = await request<{ id: string }>(token, workspace, {
                path,
              });
              refresh();
              location.hash = link({ batch: value.id });
              setPath("");
            } catch (reason) {
              setError(String(reason));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            批次目录
            <input
              required
              placeholder="包含 batch.json 的服务器绝对目录"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
          </label>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "检查中…" : "登记批次"}
          </button>
        </form>
        <Notice error={error} />
        <small>登记不会启动运行；支持来自不同状态目录的实验。</small>
      </details>
      {batches.length > 0 && <BatchNotifications batches={batches} />}
    </>
  );
}
