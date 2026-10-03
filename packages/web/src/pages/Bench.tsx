// Benchmark jobs: job list, one job's task × method matrix, and method comparison across jobs.
// Only `valid` trials enter means; invalid / unknown trials are shown with their issues.
import { useEffect, useMemo, useState } from "react";
import { IconAlert, IconCompare, IconFlask } from "../components/icons.tsx";
import { TopBar } from "../components/TopBar.tsx";
import { Empty, Link, Loading, toast } from "../components/ui.tsx";
import {
  api,
  type BenchJob,
  type BenchJobList,
  type MethodSummary,
  type Outcome,
  type Trial,
} from "../lib/api.ts";
import { ago, dateTime, duration, jobPath, runPath } from "../lib/format.ts";
import { navigate, onLinkClick, setQuery, useLocation } from "../lib/router.ts";
import { useAsync } from "../lib/use.ts";

const pctOf = (o: Outcome | null) =>
  o && o.score !== null && o.maxScore > 0 ? (100 * o.score) / o.maxScore : null;
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);
const jobLabel = (j: BenchJob) => j.spec.name ?? j.id;

function JobState({ state }: { state: BenchJob["state"] }) {
  const cls = state === "done" ? "good" : state === "cancelled" ? "warn" : "";
  return <span className={`chip ${cls}`}>{state}</span>;
}

/** Stacked valid / invalid / unknown / pending bar. */
function EvalBar({ s }: { s: MethodSummary }) {
  const part = (n: number, c: string, label: string) =>
    n > 0 && (
      <span title={`${n} ${label}`} style={{ width: `${(100 * n) / s.trials}%`, background: c }} />
    );
  return (
    <div className="evalbar">
      {part(s.valid, "var(--st-succeeded)", "valid")}
      {part(s.invalid, "var(--st-failed)", "invalid")}
      {part(s.unknown, "var(--st-cancelled)", "unknown")}
      {part(s.pending, "var(--st-queued)", "pending")}
    </div>
  );
}

function ScoreCell({
  pct,
  evaluation,
  href,
  title,
  note,
}: {
  pct: number | null;
  evaluation: Outcome["evaluation"] | "pending";
  href?: string;
  title?: string;
  note?: string;
}) {
  const cls = evaluation === "valid" ? "" : evaluation;
  const text =
    evaluation === "pending"
      ? "…"
      : evaluation === "valid"
        ? fmtPct(pct)
        : evaluation === "invalid"
          ? "invalid"
          : "unknown";
  const style = { "--p": (pct ?? 0) / 100 } as React.CSSProperties;
  const body = (
    <>
      {text}
      {note && <span className="n">{note}</span>}
    </>
  );
  return href ? (
    <Link href={href} className={`score ${cls}`} style={style} title={title}>
      {body}
    </Link>
  ) : (
    <span className={`score ${cls}`} style={style} title={title}>
      {body}
    </span>
  );
}

const CLI_HINT = [
  "orbit bench add tbs /path/to/terminal-bench-science --adapter harbor",
  "orbit bench add mine /path/to/benchmark --adapter /path/to/adapter.py",
  "orbit bench run tbs -m oracle -m empty -m codex=codex,auth=<profile>,model=<model>",
];

// ---- /bench ----

export function BenchJobs() {
  const jobs = useAsync(() => api.benchJobs(), [], { poll: true, pollMs: 4000 });
  const benchmarks = useAsync(() => api.benchmarks(), []);
  const loc = useLocation();
  const selected = (loc.query.get("sel") ?? "").split(",").filter(Boolean);
  const toggle = (id: string) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    setQuery({ sel: next.join(",") || null });
  };

  return (
    <>
      <TopBar crumbs={[{ label: "Bench" }]}>
        <button
          type="button"
          className="btn sm"
          disabled={selected.length === 0}
          onClick={() =>
            navigate(`/bench/compare?jobs=${selected.map(encodeURIComponent).join(",")}`)
          }
        >
          <IconCompare size={14} /> Compare{selected.length ? ` (${selected.length})` : ""}
        </button>
      </TopBar>
      <div className="page">
        <div className="page-pad col" style={{ gap: 16 }}>
          {jobs.error && <div className="callout">{jobs.error}</div>}
          {!jobs.data ? (
            <Loading what="Loading bench jobs" />
          ) : jobs.data.length === 0 ? (
            <Empty title="No benchmark jobs yet" icon={<IconFlask size={36} />}>
              <p>Register a benchmark and run methods on it from the CLI:</p>
              {CLI_HINT.map((c) => (
                <p key={c}>
                  <code>{c}</code>
                </p>
              ))}
            </Empty>
          ) : (
            <section className="card">
              <div className="card-h">
                Jobs <span className="sub">{jobs.data.length}</span>
              </div>
              <JobTable jobs={jobs.data} selected={selected} toggle={toggle} />
            </section>
          )}
          <section className="card">
            <div className="card-h">
              Benchmarks <span className="sub">{benchmarks.data?.length ?? 0}</span>
            </div>
            {!benchmarks.data?.length ? (
              <div className="card-b faint">
                None registered. <code>{CLI_HINT[0]}</code>
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Adapter</th>
                    <th>Path</th>
                    <th className="r">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarks.data.map((b) => (
                    <tr key={b.name}>
                      <td>
                        <b>{b.name}</b>
                      </td>
                      <td>
                        <span className="chip mono" title={b.adapter}>
                          {b.adapter.startsWith("/") ? b.adapter.split("/").pop() : b.adapter}
                        </span>
                      </td>
                      <td className="mono faint ellipsis">{b.path}</td>
                      <td className="r faint">{ago(b.updatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function JobTable({
  jobs,
  selected,
  toggle,
}: {
  jobs: BenchJobList["jobs"];
  selected: string[];
  toggle: (id: string) => void;
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th style={{ width: 28 }} />
          <th>Job</th>
          <th>Benchmark</th>
          <th>State</th>
          <th>Methods (mean over valid · valid/total)</th>
          <th className="r">Created</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <tr
            key={j.id}
            className={`click${selected.includes(j.id) ? " sel" : ""}`}
            onClick={() => navigate(jobPath(j.id))}
          >
            <td onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                aria-label="Select for compare"
                checked={selected.includes(j.id)}
                onChange={() => toggle(j.id)}
              />
            </td>
            <td>
              <Link
                href={jobPath(j.id)}
                style={{ color: "var(--text)", fontWeight: 600 }}
                onClick={(e) => {
                  e.stopPropagation();
                  onLinkClick(e);
                }}
              >
                {jobLabel(j)}
              </Link>
              {j.spec.name && <div className="mono faint">{j.id}</div>}
            </td>
            <td>{j.spec.benchmark}</td>
            <td>
              <JobState state={j.state} />
            </td>
            <td>
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                {j.summary.map((s) => (
                  <span key={s.method} className="chip" title={summaryTitle(s)}>
                    {s.method} <b>{fmtPct(s.meanPct)}</b>
                    <span className="faint">
                      {s.valid}/{s.trials}
                    </span>
                  </span>
                ))}
              </div>
            </td>
            <td className="r faint">{ago(j.createdAt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const summaryTitle = (s: MethodSummary) =>
  `${s.valid} valid · ${s.invalid} invalid · ${s.unknown} unknown · ${s.pending} pending`;

// ---- /bench/<id> ----

export function BenchJobDetail({ id }: { id: string }) {
  const [running, setRunning] = useState(true);
  const d = useAsync(() => api.benchJob(id), [id], { poll: running, pollMs: 3000 });
  const job = d.data?.job;
  // A finished job no longer changes: stop polling it.
  useEffect(() => {
    if (job) setRunning(job.state === "running");
  }, [job]);
  const trials = d.data?.trials ?? [];
  const methods = job?.spec.methods.map((m) => m.name) ?? [];
  const tasks = useMemo(() => [...new Set(trials.map((t) => t.task))], [trials]);
  const cells = useMemo(() => {
    const m = new Map<string, Trial[]>();
    for (const t of trials) {
      const k = `${t.task}\u0000${t.method}`;
      m.set(k, [...(m.get(k) ?? []), t]);
    }
    return m;
  }, [trials]);
  const problems = trials.filter(
    (t) => (t.outcome && t.outcome.evaluation !== "valid") || (t.outcome?.issues.length ?? 0) > 0,
  );

  if (d.error && !d.data)
    return (
      <>
        <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: id }]} />
        <Empty title="Bench job not found">{d.error}</Empty>
      </>
    );
  if (!d.data || !job)
    return (
      <>
        <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: id }]} />
        <Loading />
      </>
    );

  const cancel = async () => {
    try {
      await api.benchCancel(job.id);
      toast("Job cancelled");
      d.reload();
    } catch (e) {
      toast((e as Error).message);
    }
  };
  const end = job.endedAt ? Date.parse(job.endedAt) : Date.now();

  return (
    <>
      <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: jobLabel(job) }]}>
        <Link className="btn sm ghost" href={`/?q=bench-${job.id}`}>
          Runs
        </Link>
        <Link className="btn sm" href={`/bench/compare?jobs=${job.id}`}>
          <IconCompare size={14} /> Compare
        </Link>
        {job.state === "running" && (
          <button type="button" className="btn sm danger" onClick={cancel}>
            Cancel job
          </button>
        )}
      </TopBar>
      <div className="page">
        <div className="page-pad col" style={{ gap: 16 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <JobState state={job.state} />
            <span className="chip mono">{job.spec.benchmark}</span>
            <span className="faint">
              {tasks.length} tasks × {methods.length} methods × {job.spec.seeds} seed
              {job.spec.seeds > 1 ? "s" : ""} · started {dateTime(job.createdAt)} ·{" "}
              {duration(end - Date.parse(job.createdAt))}
            </span>
            {Object.entries(job.spec.options).map(([k, v]) => (
              <span key={k} className="chip mono">
                {k}={v}
              </span>
            ))}
          </div>

          <div className="stats">
            {d.data.summary.map((s) => {
              const m = job.spec.methods.find((x) => x.name === s.method);
              return (
                <div key={s.method} className="card card-b stat" title={summaryTitle(s)}>
                  <span className="l">
                    <b style={{ color: "var(--text)" }}>{s.method}</b>
                    {m && (
                      <span className="mono">
                        {" "}
                        · {m.agent}
                        {m.model ? ` · ${m.model}` : ""}
                        {m.effort ? ` · ${m.effort}` : ""}
                      </span>
                    )}
                  </span>
                  <span className="v">{fmtPct(s.meanPct)}</span>
                  <EvalBar s={s} />
                  <span className="l">
                    {s.valid} valid · {s.invalid} invalid · {s.unknown} unknown
                    {s.pending ? ` · ${s.pending} pending` : ""}
                  </span>
                </div>
              );
            })}
          </div>

          <section className="card">
            <div className="card-h">
              Scores <span className="sub">percent of max · click a cell for its solve run</span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="table matrix">
                <thead>
                  <tr>
                    <th>Task</th>
                    {methods.map((m) => (
                      <th key={m}>{m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => (
                    <tr key={task}>
                      <td className="mono">{task}</td>
                      {methods.map((m) => (
                        <td key={m}>
                          <div className="row" style={{ gap: 4, justifyContent: "center" }}>
                            {(cells.get(`${task}\u0000${m}`) ?? []).map((t) => (
                              <TrialCell key={t.id} t={t} seeds={job.spec.seeds} />
                            ))}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr className="mean">
                    <td>Mean (valid)</td>
                    {d.data.summary.map((s) => (
                      <td key={s.method}>
                        <ScoreCell
                          pct={s.meanPct}
                          evaluation={s.meanPct === null ? "unknown" : "valid"}
                          note={`${s.valid}/${s.trials}`}
                        />
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {problems.length > 0 && (
            <section className="card">
              <div className="card-h">
                <IconAlert size={14} /> Issues <span className="sub">{problems.length} trials</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Method</th>
                    <th>Evaluation</th>
                    <th>Execution</th>
                    <th>Issues</th>
                    <th>Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {problems.map((t) => (
                    <tr key={t.id}>
                      <td className="mono">{t.task}</td>
                      <td>
                        {t.method}
                        {job.spec.seeds > 1 && <span className="faint"> #{t.seed}</span>}
                      </td>
                      <td>
                        <span
                          className={`chip ${t.outcome?.evaluation === "valid" ? "good" : t.outcome?.evaluation === "invalid" ? "bad" : "warn"}`}
                        >
                          {t.outcome?.evaluation}
                        </span>
                      </td>
                      <td className="mono">{t.outcome?.execution}</td>
                      <td className="muted" style={{ whiteSpace: "normal" }}>
                        {t.outcome?.issues.join("; ")}
                      </td>
                      <td>
                        <RunLinks t={t} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function RunLinks({ t }: { t: Trial }) {
  return (
    <span className="row" style={{ gap: 6 }}>
      {t.solveRunId && (
        <Link className="chip link mono" href={runPath(t.solveRunId)}>
          solve
        </Link>
      )}
      {t.verifyRunId && (
        <Link className="chip link mono" href={runPath(t.verifyRunId)}>
          verify
        </Link>
      )}
    </span>
  );
}

function TrialCell({ t, seeds }: { t: Trial; seeds: number }) {
  const o = t.outcome;
  const phase = t.state === "done" ? null : t.state;
  const title = [
    `${t.task} · ${t.method}${seeds > 1 ? ` #${t.seed}` : ""}`,
    phase ? `state: ${phase}` : `evaluation: ${o?.evaluation} · execution: ${o?.execution}`,
    o && o.score !== null ? `score: ${o.score} / ${o.maxScore}` : null,
    ...(o?.issues ?? t.issues),
    o?.cleanup === "failed" ? "cleanup failed" : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <ScoreCell
      pct={pctOf(o)}
      evaluation={o ? o.evaluation : "pending"}
      href={t.solveRunId ? runPath(t.solveRunId) : undefined}
      title={title}
      note={phase === "verifying" ? "verify" : seeds > 1 ? `#${t.seed}` : undefined}
    />
  );
}

// ---- /bench/compare?jobs=a,b ----

export function BenchComparePage() {
  const loc = useLocation();
  const ids = (loc.query.get("jobs") ?? "").split(",").filter(Boolean);
  const key = ids.join(",");
  const jobs = useAsync(() => api.benchJobs(), []);
  // Results change only while a selected job runs (unknown jobs count as running).
  const live = ids.some(
    (id) => (jobs.data?.find((j) => j.id === id)?.state ?? "running") === "running",
  );
  const cmp = useAsync(() => (ids.length ? api.benchCompare(ids) : Promise.resolve(null)), [key], {
    poll: live,
    pollMs: 5000,
  });
  const toggle = (id: string) => {
    const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
    setQuery({ jobs: next.join(",") || null });
  };
  const c = cmp.data;
  const base = c?.columns[0]?.key;

  return (
    <>
      <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: "Compare methods" }]} />
      <div className="page">
        <div className="page-pad col" style={{ gap: 16 }}>
          <section className="col" style={{ gap: 8 }}>
            <h3 className="section-title">Jobs</h3>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {(jobs.data ?? []).map((j) => (
                <button
                  key={j.id}
                  type="button"
                  className={`btn sm${ids.includes(j.id) ? " on" : " ghost"}`}
                  onClick={() => toggle(j.id)}
                  title={`${j.spec.benchmark} · ${j.state}`}
                >
                  {jobLabel(j)} <span className="faint">{j.spec.benchmark}</span>
                </button>
              ))}
            </div>
          </section>
          {ids.length === 0 ? (
            <Empty title="Pick jobs to compare" icon={<IconCompare size={36} />}>
              Methods of the selected jobs are compared task by task on valid trials.
            </Empty>
          ) : cmp.error ? (
            <div className="callout">{cmp.error}</div>
          ) : !c ? (
            <Loading />
          ) : (
            <>
              <div className="callout" style={{ "--c": "var(--accent)" } as React.CSSProperties}>
                Cells are mean percent over valid trials (valid/total below). <b>Paired</b> means
                use only the {c.pairedTasks} task{c.pairedTasks === 1 ? "" : "s"} valid in every
                column; Δ is relative to <b>{base}</b>.
              </div>
              <section className="card">
                <div style={{ overflowX: "auto" }}>
                  <table className="table matrix">
                    <thead>
                      <tr>
                        <th>Task</th>
                        {c.columns.map((col) => (
                          <th key={col.key}>
                            <Link href={jobPath(col.jobId)}>{col.key}</Link>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {c.rows.map((r) => {
                        const vals = c.columns
                          .map((col) => r.cells[col.key])
                          .filter((x): x is number => x != null);
                        const best = vals.length > 1 ? Math.max(...vals) : null;
                        return (
                          <tr key={r.task}>
                            <td className="mono">{r.task}</td>
                            {c.columns.map((col) => {
                              const v = r.cells[col.key] ?? null;
                              const n = r.counts[col.key] ?? "";
                              return (
                                <td key={col.key}>
                                  {n === "" ? (
                                    <span className="faint">—</span>
                                  ) : (
                                    <ScoreCell
                                      pct={v}
                                      evaluation={v === null ? "unknown" : "valid"}
                                      note={n}
                                      title={
                                        v === null
                                          ? "no valid trial (pending, invalid or unknown)"
                                          : v === best
                                            ? "best in row"
                                            : undefined
                                      }
                                    />
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                      {(["all", "paired"] as const).map((kind) => (
                        <tr key={kind} className="mean">
                          <td>
                            {kind === "all"
                              ? "Mean (all valid)"
                              : `Mean (paired, ${c.pairedTasks})`}
                          </td>
                          {c.columns.map((col) => {
                            const v = c.means[col.key]?.[kind] ?? null;
                            const b = base ? (c.means[base]?.[kind] ?? null) : null;
                            const delta =
                              col.key !== base && v !== null && b !== null ? v - b : null;
                            return (
                              <td key={col.key}>
                                <div className="col" style={{ alignItems: "center", gap: 2 }}>
                                  <ScoreCell
                                    pct={v}
                                    evaluation={v === null ? "unknown" : "valid"}
                                  />
                                  {delta !== null && (
                                    <span
                                      className={`mono delta ${delta > 0 ? "up" : delta < 0 ? "down" : ""}`}
                                      style={{ fontSize: 11 }}
                                    >
                                      {delta > 0 ? "+" : ""}
                                      {delta.toFixed(1)} pt
                                    </span>
                                  )}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <MeanBars c={c} />
            </>
          )}
        </div>
      </div>
    </>
  );
}

/** Horizontal bars of the paired (or, without paired tasks, all-valid) means. */
function MeanBars({ c }: { c: NonNullable<Awaited<ReturnType<typeof api.benchCompare>>> }) {
  const kind = c.pairedTasks > 0 ? "paired" : "all";
  const vals = c.columns.map((col) => ({ key: col.key, v: c.means[col.key]?.[kind] ?? null }));
  return (
    <section className="card">
      <div className="card-h">
        Mean score{" "}
        <span className="sub">{kind === "paired" ? "paired tasks" : "all valid tasks"}</span>
      </div>
      <div className="card-b col" style={{ gap: 8 }}>
        {vals.map(({ key, v }) => (
          <div key={key} className="row" style={{ gap: 10 }}>
            <span className="mono ellipsis" style={{ width: 220 }}>
              {key}
            </span>
            <div style={{ flex: 1, background: "var(--surface-3)", borderRadius: 4, height: 14 }}>
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, v ?? 0))}%`,
                  height: "100%",
                  borderRadius: 4,
                  background: "var(--accent)",
                }}
              />
            </div>
            <span className="mono" style={{ width: 64, textAlign: "right" }}>
              {fmtPct(v)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
