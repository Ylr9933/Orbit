import { useState } from "react";
import { request, useData } from "../api/console";
import { Empty, Notice } from "../components/common";
import { BatchResults } from "./benchmark/batch-detail";
import { Trend } from "./benchmark/charts";
import { ComparisonPanel } from "./benchmark/comparison";
import { BatchNotifications } from "./benchmark/notifications";
import { RunDetail } from "./benchmark/run-detail";
import type { BatchDetail, Overview } from "./benchmark/types";
import { link, number, workspace } from "./benchmark/utils";
import { BenchmarkDiagnostics } from "./benchmark-diagnostics";
import "./benchmark/workspace.css";

export function BenchmarksPage({
  token,
  route = "benchmarks",
}: {
  token: string;
  route?: string;
}) {
  const params = Object.fromEntries(
    new URLSearchParams(route.split("?")[1] ?? ""),
  );
  const overview = useData<Overview>(token, workspace, 5000);
  const [failure, setFailure] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState(false);
  const [batchSearch, setBatchSearch] = useState("");
  const batches = overview.data?.batches ?? [];
  const selected =
    batches.find((b) => b.id === params.batch) ??
    (params.batch ? undefined : batches[0]);
  const batch = useData<BatchDetail>(
    token,
    selected ? `${workspace}/${selected.id}` : null,
    selected && selected.finished === selected.total ? 0 : 5000,
  );
  const baselineId = params.baseline ?? overview.data?.settings.baseline ?? "";
  const baseline = batches.find((b) => b.id === baselineId);
  const metrics = [
    ...new Set([
      ...Object.keys(selected?.metrics ?? {}),
      ...Object.keys(baseline?.metrics ?? {}),
    ]),
  ];
  const metric = params.metric || metrics[0] || "";
  const currentIndex =
    batch.data?.runs.findIndex((r) => r.run_id === params.run) ?? -1;
  const previous = batch.data?.runs
    .slice(0, Math.max(0, currentIndex))
    .reverse()
    .find((r) => r.run_id);
  const next =
    currentIndex >= 0
      ? batch.data?.runs.slice(currentIndex + 1).find((r) => r.run_id)
      : undefined;
  const update = (values: Record<string, string | null>) => {
    location.hash = link({ ...params, batch: selected?.id, ...values });
  };
  function saved() {
    overview.refresh();
    batch.refresh();
  }
  return (
    <div className="benchmark-workspace">
      <div className="section-line">
        <div>
          <h2>实验与评测</h2>
          <p className="muted">
            从批次结果追到每一道题，比较改动，复盘 Agent 行为。
          </p>
        </div>
        <button type="button" onClick={saved}>
          刷新结果
        </button>
      </div>
      <Notice error={failure || overview.error} loading={!overview.data} />
      {overview.data?.errors.map((e) => (
        <p className="bench-warning" key={e.id}>
          批次 {e.id} 无法读取：{e.message}
        </p>
      ))}
      <details className="bench-register" open={!batches.length}>
        <summary>登记已有批次</summary>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setFailure("");
            try {
              const value = await request<{ id: string }>(token, workspace, {
                path,
              });
              overview.refresh();
              location.hash = link({ batch: value.id });
              setPath("");
            } catch (reason) {
              setFailure(String(reason));
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
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "检查中…" : "登记批次"}
          </button>
        </form>
        <small>登记已有实验供查看与比较，不启动运行。支持不同状态目录。</small>
      </details>
      {!batches.length && overview.data && (
        <Empty>
          还没有可查看的实验。登记一个已准备的批次，或连接已有 Benchmark
          状态目录。
        </Empty>
      )}
      {batches.length > 0 && <BatchNotifications batches={batches} />}
      {batches.length > 0 && (
        <>
          <details className="bench-batches" open={!params.run}>
            <summary>实验批次 · {batches.length}</summary>
            <label>
              搜索实验
              <input
                type="search"
                placeholder="名称、模型、标签或研究项目"
                value={batchSearch}
                onChange={(e) => setBatchSearch(e.target.value)}
              />
            </label>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>实验</th>
                    <th>模型 / Benchmark</th>
                    <th>已结束 / 总任务</th>
                    <th>有效评分</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {batches
                    .filter((b) =>
                      `${b.name} ${b.models} ${b.annotation.tags ?? ""} ${b.annotation.project ?? ""}`
                        .toLowerCase()
                        .includes(batchSearch.toLowerCase()),
                    )
                    .map((b) => (
                      <tr
                        key={b.id}
                        className={
                          selected?.id === b.id ? "bench-selected" : ""
                        }
                      >
                        <td>
                          <a
                            href={link({
                              batch: b.id,
                              baseline: baselineId,
                              metric,
                            })}
                          >
                            {b.name}
                          </a>
                          {b.id === baselineId && (
                            <span className="badge">基线</span>
                          )}
                          <small>
                            {b.annotation.tags} {b.annotation.project}
                          </small>
                        </td>
                        <td>
                          {b.models.join(", ")}
                          <small>{b.benchmarks.join(", ")}</small>
                        </td>
                        <td>
                          {b.finished} / {b.total}
                          <progress
                            aria-label={`${b.name} 完成进度`}
                            value={b.finished}
                            max={b.total || 1}
                          />
                        </td>
                        <td>
                          {b.scored} / {b.total}
                        </td>
                        <td>
                          {b.created_at
                            ? new Date(b.created_at).toLocaleString()
                            : "尚未提交"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </details>
          {!selected && (
            <Empty>链接中的批次不存在。请在列表中选择，或登记对应批次。</Empty>
          )}
          {selected && (
            <>
              <div className="section-line">
                <h2>{selected.name}</h2>
                <div className="actions">
                  <button
                    type="button"
                    onClick={async () => {
                      setFailure("");
                      try {
                        await request(token, `${workspace}/settings`, {
                          baseline: selected.id,
                          revision: overview.data?.settings.revision ?? 0,
                        });
                        overview.refresh();
                        update({ baseline: selected.id });
                      } catch (reason) {
                        setFailure(String(reason));
                      }
                    }}
                  >
                    设为基线
                  </button>
                  {params.run && (
                    <a
                      href={link({
                        batch: selected.id,
                        baseline: baselineId,
                        metric,
                      })}
                    >
                      返回批次结果
                    </a>
                  )}
                </div>
              </div>
              <div className="bench-filters">
                <label>
                  评分指标
                  <select
                    value={metric}
                    onChange={(e) => update({ metric: e.target.value })}
                  >
                    {metrics.length ? (
                      metrics.map((m) => <option key={m}>{m}</option>)
                    ) : (
                      <option value="">尚无评分</option>
                    )}
                  </select>
                </label>
                <label>
                  对比基线
                  <select
                    value={baselineId}
                    onChange={(e) =>
                      update({
                        baseline: e.target.value,
                        run: null,
                        peer: null,
                        peerBatch: null,
                      })
                    }
                  >
                    <option value="">不比较</option>
                    {batches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="muted">
                  有效评分 {selected.scored}/{selected.total} · 当前已评分均值{" "}
                  {number(selected.metrics[metric]?.mean)}
                  {selected.finished < selected.total ? "（批次未完成）" : ""}
                </span>
              </div>
              <Notice error={batch.error} loading={!batch.data} />
              {params.run && (
                <div className="actions">
                  {previous?.run_id && (
                    <a
                      href={link({
                        batch: selected.id,
                        run: previous.run_id,
                        baseline: baselineId,
                        metric,
                      })}
                    >
                      ← 上一题
                    </a>
                  )}
                  {next?.run_id && (
                    <a
                      href={link({
                        batch: selected.id,
                        run: next.run_id,
                        baseline: baselineId,
                        metric,
                      })}
                    >
                      下一题 →
                    </a>
                  )}
                </div>
              )}
              {params.run ? (
                <div
                  className={
                    params.peer && params.peerBatch ? "bench-compare-runs" : ""
                  }
                >
                  {params.peer && params.peerBatch && (
                    <RunDetail
                      key={params.peer}
                      token={token}
                      batch={params.peerBatch}
                      runId={params.peer}
                      params={{ batch: params.peerBatch, run: params.peer }}
                      saved={saved}
                      title="基线实验"
                    />
                  )}
                  <RunDetail
                    key={params.run}
                    token={token}
                    batch={selected.id}
                    runId={params.run}
                    params={params}
                    note={
                      batch.data?.runs.find((r) => r.run_id === params.run)
                        ?.annotation
                    }
                    saved={saved}
                  />
                </div>
              ) : (
                <>
                  <Trend
                    batches={batches}
                    selected={selected}
                    metric={metric}
                  />
                  {baseline && baseline.id !== selected.id && metric && (
                    <ComparisonPanel
                      key={`${baseline.id}-${selected.id}-${metric}`}
                      token={token}
                      baseline={baseline}
                      candidate={selected}
                      metric={metric}
                    />
                  )}
                  {batch.data && (
                    <BatchResults
                      key={selected.id}
                      token={token}
                      batch={batch.data}
                      metric={metric}
                      baseline={baselineId}
                      saved={saved}
                    />
                  )}
                </>
              )}
            </>
          )}
        </>
      )}
      <details onToggle={(e) => setDiagnostics(e.currentTarget.open)}>
        <summary>运行诊断、Campaign 与兼容性</summary>
        {diagnostics && <BenchmarkDiagnostics token={token} />}
      </details>
    </div>
  );
}
