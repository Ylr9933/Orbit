import { useEffect, useState } from "react";
import { request, useData } from "../api/console";
import { Empty, Notice } from "../components/common";
import { BatchResults } from "./benchmark/batch-detail";
import { BatchHeader } from "./benchmark/batch-header";
import { BatchList } from "./benchmark/batch-list";
import { ScoreDistribution } from "./benchmark/batch-summary";
import { Trend } from "./benchmark/charts";
import { ComparisonPanel } from "./benchmark/comparison";
import { Notes } from "./benchmark/notes";
import { batchTitle, resultRows } from "./benchmark/presentation";
import { RunDetail } from "./benchmark/run-detail";
import type { BatchDetail, Overview } from "./benchmark/types";
import { link, workspace } from "./benchmark/utils";
import { BenchmarkDiagnostics } from "./benchmark-diagnostics";
import "./benchmark/workspace.css";

function settled(value: Overview) {
  return (
    !value.errors.length && value.batches.every((b) => b.finished === b.total)
  );
}
function finished(value: BatchDetail) {
  return value.finished === value.total;
}

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
  const overview = useData<Overview>(token, workspace, 5000, settled);
  const batches = overview.data?.batches ?? [];
  const selected = batches.find((b) => b.id === params.batch);
  const batch = useData<BatchDetail>(
    token,
    selected ? `${workspace}/${selected.id}` : null,
    5000,
    finished,
  );
  const [failure, setFailure] = useState("");
  const [diagnostics, setDiagnostics] = useState(false);
  const baselineId = params.baseline ?? overview.data?.settings.baseline ?? "";
  const baseline = batches.find((b) => b.id === baselineId);
  const metrics = [
    ...new Set([
      ...Object.keys(selected?.metrics ?? {}),
      ...Object.keys(baseline?.metrics ?? {}),
    ]),
  ];
  const metric = params.metric || metrics[0] || "";
  const tab = params.tab || "results";
  const effective = { ...params, baseline: baselineId, metric };
  const rows = resultRows(batch.data?.runs ?? [], metric, params).filter(
    (r) => r.run_id,
  );
  const index = rows.findIndex((r) => r.run_id === params.run);
  const previous = index > 0 ? rows[index - 1] : undefined,
    next = index >= 0 ? rows[index + 1] : undefined;
  const update = (values: Record<string, string | null>) => {
    const hash = link({ ...effective, ...values });
    // Editing filters replaces the current history entry; opening a task/tab creates one.
    history.replaceState(
      null,
      "",
      `${location.pathname}${location.search}${hash}`,
    );
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };
  function saved() {
    overview.refresh();
    batch.refresh();
  }
  useEffect(() => {
    if (params.run) window.scrollTo(0, 0);
  }, [params.run]);
  const back = {
    ...effective,
    run: null,
    peer: null,
    peerBatch: null,
    view: null,
    step: null,
    cursor: null,
    traceSearch: null,
    traceKind: null,
  };
  return (
    <div className="benchmark-workspace">
      <div className="workbench-breadcrumb">
        <div>
          <a href="#benchmarks">实验</a>
          {params.batch && (
            <>
              {" "}
              <span>/</span>{" "}
              <a href={link(back)}>
                {selected ? batchTitle(selected, batch.data?.runs) : "实验详情"}
              </a>
            </>
          )}
          {params.run && (
            <>
              {" "}
              <span>/</span> <span>任务详情</span>
            </>
          )}
        </div>
        {!params.run && (
          <button type="button" onClick={saved}>
            刷新结果
          </button>
        )}
      </div>
      <Notice error={failure || overview.error} loading={!overview.data} />
      {overview.data?.errors.map((e) => (
        <p className="bench-warning" key={e.id}>
          实验暂时无法读取：{e.message}
        </p>
      ))}
      {!params.batch ? (
        <>
          <BatchList
            token={token}
            batches={batches}
            baseline={baselineId}
            refresh={overview.refresh}
          />
          <details onToggle={(e) => setDiagnostics(e.currentTarget.open)}>
            <summary>高级诊断与兼容性</summary>
            {diagnostics && <BenchmarkDiagnostics token={token} />}
          </details>
        </>
      ) : !selected && overview.data ? (
        <Empty>
          找不到这个实验，请<a href="#benchmarks">返回实验列表</a>登记对应批次。
        </Empty>
      ) : (
        selected && (
          <>
            {!params.run && (
              <BatchHeader
                selected={selected}
                detail={batch.data}
                metric={metric}
                metrics={metrics}
                params={effective}
                update={update}
              />
            )}
            <Notice error={batch.error} loading={!batch.data} />
            {params.run ? (
              <>
                <div className="task-navigation">
                  <a href={link(back)}>← 返回批次结果</a>
                  <div className="actions">
                    {previous?.run_id && (
                      <a
                        href={link({
                          ...effective,
                          run: previous.run_id,
                          step: null,
                          cursor: null,
                          peer: null,
                          peerBatch: null,
                        })}
                      >
                        ← 上一题
                      </a>
                    )}
                    {next?.run_id && (
                      <a
                        href={link({
                          ...effective,
                          run: next.run_id,
                          step: null,
                          cursor: null,
                          peer: null,
                          peerBatch: null,
                        })}
                      >
                        下一题 →
                      </a>
                    )}
                  </div>
                </div>
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
                      params={{
                        batch: params.peerBatch,
                        run: params.peer,
                        view: "trace",
                      }}
                      saved={saved}
                      title="基线实验"
                    />
                  )}
                  <RunDetail
                    key={params.run}
                    token={token}
                    batch={selected.id}
                    runId={params.run}
                    params={effective}
                    note={
                      batch.data?.runs.find((r) => r.run_id === params.run)
                        ?.annotation
                    }
                    saved={saved}
                  />
                </div>
              </>
            ) : (
              <>
                {tab === "results" && batch.data && (
                  <BatchResults
                    batch={batch.data}
                    metric={metric}
                    params={effective}
                    update={update}
                  />
                )}
                {tab === "distribution" && batch.data && (
                  <ScoreDistribution batch={batch.data} metric={metric} />
                )}
                {tab === "notes" && (
                  <Notes
                    key={selected.id}
                    token={token}
                    batch={selected.id}
                    initial={selected.annotation}
                    saved={saved}
                  />
                )}
                {tab === "comparison" && (
                  <>
                    <div className="bench-filters">
                      <label>
                        对比基线
                        <select
                          value={baselineId === selected.id ? "" : baselineId}
                          onChange={(e) => update({ baseline: e.target.value })}
                        >
                          <option value="">选择另一组实验</option>
                          {batches
                            .filter((b) => b.id !== selected.id)
                            .map((b) => (
                              <option key={b.id} value={b.id}>
                                {b.name}
                              </option>
                            ))}
                        </select>
                      </label>
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
                          } catch (reason) {
                            setFailure(String(reason));
                          }
                        }}
                      >
                        将当前实验设为默认基线
                      </button>
                    </div>
                    {baseline && baseline.id !== selected.id && metric ? (
                      <ComparisonPanel
                        key={`${baseline.id}-${selected.id}-${metric}`}
                        token={token}
                        baseline={baseline}
                        candidate={selected}
                        metric={metric}
                      />
                    ) : (
                      <Empty>
                        {batches.length < 2
                          ? "还没有第二组实验。登记另一组结果后，可逐题比较分数、配置和轨迹。"
                          : "请选择另一组实验作为基线。"}
                      </Empty>
                    )}
                    {batches.length > 1 && (
                      <details>
                        <summary>同任务集的历史均分</summary>
                        <Trend
                          batches={batches}
                          selected={selected}
                          metric={metric}
                        />
                      </details>
                    )}
                  </>
                )}
                <div className="workbench-footnote">
                  <span>
                    最近读取 {batch.updated || "—"}
                    {selected.finished < selected.total
                      ? " · 每 5 秒更新"
                      : " · 已完成，按需刷新"}
                  </span>
                  <span>有效评分的描述性均值，不是官方套件总分。</span>
                </div>
              </>
            )}
          </>
        )
      )}
    </div>
  );
}
