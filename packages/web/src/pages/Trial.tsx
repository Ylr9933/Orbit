// One bench trial (task × method × seed) on one page: its outcome and issues, the solve → verify
// timeline with measured use, the report the solve produced (Markdown with its figures), the
// grader's per-item scores when it writes them, and the session of the Agent inside the solve.
import { useEffect, useMemo, useState } from "react";
import { IconAlert, IconFile, IconFlask } from "../components/icons.tsx";
import { joinPath, Markdown } from "../components/Markdown.tsx";
import { TopBar } from "../components/TopBar.tsx";
import { Empty, Link, Loading, StateBadge, useNow } from "../components/ui.tsx";
import { api, fileUrl, type Run, type Trial } from "../lib/api.ts";
import {
  dateTime,
  duration,
  fmtScore,
  isActive,
  jobPath,
  runDuration,
  runPath,
} from "../lib/format.ts";
import { reportCandidates } from "../lib/report.ts";
import { setQuery, useLocation } from "../lib/router.ts";
import { upsertRun, useRun } from "../lib/runs-store.ts";
import { useAsync } from "../lib/use.ts";
import { SessionTab } from "./run/Session.tsx";

export const trialPath = (jobId: string, trialId: string) =>
  `${jobPath(jobId)}/trials/${encodeURIComponent(trialId)}`;

const TABS = ["report", "judge", "session"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  report: "Report",
  judge: "Grader",
  session: "Agent session",
};

/** A run from the live store, else fetched once. */
function useRunOnce(id: string | null): Run | undefined {
  const live = useRun(id ?? "");
  const [fetched, setFetched] = useState<Run>();
  useEffect(() => {
    if (!id || live) return;
    api.run(id).then(
      (r) => {
        setFetched(r);
        upsertRun(r);
      },
      () => undefined,
    );
  }, [id, live]);
  return id ? (live ?? fetched) : undefined;
}

export function TrialPage({ jobId, trialId }: { jobId: string; trialId: string }) {
  const d = useAsync(() => api.benchJob(jobId), [jobId], { poll: true, pollMs: 5000 });
  const trial = d.data?.trials.find((t) => t.id === trialId);
  const job = d.data?.job;
  const solve = useRunOnce(trial?.solveRunId ?? null);
  const verify = useRunOnce(trial?.verifyRunId ?? null);
  const loc = useLocation();
  const tab = (TABS.includes(loc.query.get("tab") as Tab) ? loc.query.get("tab") : "report") as Tab;
  const now = useNow(1000, Boolean(solve && isActive(solve.state)));
  const crumbs = [
    { label: "Bench", href: "/bench" },
    { label: job?.spec.name ?? jobId, href: jobPath(jobId) },
    { label: trial ? `${trial.task} · ${trial.method}` : trialId },
  ];

  if (d.error && !d.data)
    return (
      <>
        <TopBar crumbs={crumbs} />
        <Empty title="Bench job not found">{d.error}</Empty>
      </>
    );
  if (!d.data) return <Loading />;
  if (!trial || !job)
    return (
      <>
        <TopBar crumbs={crumbs} />
        <Empty title="Trial not found">{trialId}</Empty>
      </>
    );
  const o = trial.outcome;
  const method = job.spec.methods.find((m) => m.name === trial.method);

  return (
    <>
      <TopBar crumbs={crumbs}>
        <Link className="btn sm" href={jobPath(jobId)}>
          <IconFlask size={13} /> Job
        </Link>
      </TopBar>
      <div className="run-head">
        <div className="row" style={{ gap: 12 }}>
          <EvalChip t={trial} />
          <h1 className="ellipsis">
            {trial.task} <span className="faint">·</span> {trial.method}
            {job.spec.seeds > 1 && <span className="faint"> #{trial.seed}</span>}
          </h1>
          <div className="spacer" />
          {o && o.score !== null && (
            <span className="trial-score num">
              {fmtScore(o.score)}
              <span className="faint"> / {fmtScore(o.maxScore)}</span>
            </span>
          )}
        </div>
        <div className="meta">
          <span className="chip mono">{job.spec.benchmark}</span>
          {method && (
            <span className="chip mono">
              {method.agent}
              {method.model ? ` · ${method.model}` : ""}
              {method.effort ? ` · ${method.effort}` : ""}
            </span>
          )}
          {o && <span className="chip mono">execution {o.execution}</span>}
          {o && o.cleanup !== "done" && <span className="chip warn">cleanup {o.cleanup}</span>}
          <span className="chip">{trial.state}</span>
          <span className="faint">created {dateTime(trial.createdAt)}</span>
        </div>
        {(o?.issues ?? trial.issues).length > 0 && (
          <div className={`trial-issues${o?.evaluation === "valid" ? " neutral" : ""}`}>
            <IconAlert size={13} />
            <span>{(o?.issues ?? trial.issues).join(" · ")}</span>
          </div>
        )}
        <div className="trial-timeline">
          <PhaseCard label="Solve" run={solve} id={trial.solveRunId} now={now} />
          <span className="faint">→</span>
          <PhaseCard label="Verify" run={verify} id={trial.verifyRunId} now={now} />
        </div>
      </div>
      <nav className="tabs">
        {TABS.map((t) => (
          <a
            key={t}
            href={`?tab=${t}`}
            className={tab === t ? "on" : ""}
            onClick={(e) => {
              if (e.metaKey || e.ctrlKey) return;
              e.preventDefault();
              setQuery({ tab: t === "report" ? null : t }, { replace: false, hash: "" });
            }}
          >
            {TAB_LABEL[t]}
          </a>
        ))}
      </nav>
      <div className="page" style={{ display: "flex", flexDirection: "column" }}>
        {tab === "report" &&
          (solve ? (
            <ReportView run={solve} />
          ) : (
            <Empty title="No solve run">The trial has not started a solve run.</Empty>
          ))}
        {tab === "judge" &&
          (verify ? (
            <GraderView run={verify} />
          ) : (
            <Empty title="Not verified">
              {trial.state === "done"
                ? "No verify run for this trial."
                : "Waiting for the solve run."}
            </Empty>
          ))}
        {tab === "session" && (solve ? <SessionTab run={solve} /> : <Empty title="No solve run" />)}
      </div>
    </>
  );
}

function EvalChip({ t }: { t: Trial }) {
  const e = t.outcome?.evaluation;
  const cls = e === "valid" ? "good" : e === "invalid" ? "bad" : e === "unknown" ? "warn" : "";
  return <span className={`chip ${cls}`}>{e ?? t.state}</span>;
}

function PhaseCard(props: { label: string; run: Run | undefined; id: string | null; now: number }) {
  const { run } = props;
  if (!props.id)
    return (
      <div className="card phase">
        <b>{props.label}</b> <span className="faint">not started</span>
      </div>
    );
  if (!run)
    return (
      <div className="card phase">
        <b>{props.label}</b> <span className="faint mono">{props.id}</span>
      </div>
    );
  const u = run.usage;
  return (
    <Link className="card phase" href={runPath(run.id)}>
      <div className="row" style={{ gap: 8 }}>
        <b>{props.label}</b>
        <StateBadge state={run.state} />
        <span className="spacer" />
        <span className="num muted">{duration(runDuration(run, props.now))}</span>
      </div>
      <div className="faint" style={{ fontSize: 12 }}>
        {run.spec.resources.gpus ? `${run.spec.resources.gpus} GPU · ` : ""}
        {run.spec.resources.cpus} CPU · {run.spec.resources.memGB} GB
        {u && (
          <>
            {" "}
            · peak {u.peakMemGB} GB RAM
            {u.peakGpuMemGB !== null ? ` · ${u.peakGpuMemGB} GB GPU` : ""}
            {u.oomKilled ? " · out of memory" : ""}
          </>
        )}
        {run.reason ? ` · ${run.reason}` : ""}
      </div>
    </Link>
  );
}

// ---- report ----

function useText(runId: string, path: string | undefined) {
  return useAsync(
    () =>
      path
        ? fetch(fileUrl(runId, path)).then(async (r) => {
            if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
            return r.text();
          })
        : Promise.resolve(null),
    [runId, path],
  );
}

function ReportView({ run }: { run: Run }) {
  const a = useAsync(() => api.artifacts(run.id), [run.id, run.state]);
  const candidates = useMemo(() => reportCandidates(a.data), [a.data]);
  const loc = useLocation();
  const chosen = loc.query.get("file") ?? candidates[0];
  const text = useText(run.id, chosen);
  const files = useMemo(() => new Set((a.data?.files ?? []).map((f) => f.path)), [a.data]);

  if (!a.data) return <Loading what="Loading outputs" />;
  if (!candidates.length)
    return (
      <Empty title="No report" icon={<IconFile size={30} />}>
        The solve run left no Markdown file in its outputs.{" "}
        <Link href={`${runPath(run.id)}?tab=artifacts`}>All outputs →</Link>
      </Empty>
    );
  const dir = chosen?.includes("/") ? chosen.slice(0, chosen.lastIndexOf("/")) : "";
  const resolve = (rel: string) => {
    const p = joinPath(dir, rel.split("#")[0] ?? "");
    return p && files.has(p) ? fileUrl(run.id, p) : null;
  };
  return (
    <div className="report">
      <div className="toolbar">
        <select
          className="input"
          value={chosen}
          onChange={(e) => setQuery({ file: e.target.value }, { hash: "" })}
          aria-label="Markdown file"
        >
          {candidates.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <div className="spacer" />
        <Link className="btn sm" href={`${runPath(run.id)}?tab=artifacts`}>
          All outputs
        </Link>
      </div>
      <div className="report-body">
        {text.error ? (
          <Empty title="Could not load the report">{text.error}</Empty>
        ) : text.data == null ? (
          <Loading />
        ) : (
          <Markdown text={text.data} resolve={resolve} />
        )}
      </div>
    </div>
  );
}

// ---- grader ----

interface GraderItem {
  index?: number | string;
  type?: string;
  content?: string;
  weight?: number | string;
  score?: number | string;
  reasoning?: string;
}

/** A grader result with per-item scores (e.g. ResearchClawBench `_score.json`), when present. */
function itemsOf(v: unknown): { items: GraderItem[]; total: unknown } | null {
  if (!v || typeof v !== "object") return null;
  const o = v as { items?: unknown; total_score?: unknown; score?: unknown };
  if (!Array.isArray(o.items) || !o.items.every((x) => x && typeof x === "object")) return null;
  return { items: o.items as GraderItem[], total: o.total_score ?? o.score };
}

function GraderView({ run }: { run: Run }) {
  const a = useAsync(() => api.artifacts(run.id), [run.id, run.state]);
  const jsons = useMemo(
    () =>
      (a.data?.files ?? [])
        .map((f) => f.path)
        .filter((p) => /\.json$/i.test(p) && !/(^|\/)(code|outputs|report)\//.test(p))
        .sort(
          (x, y) => Number(!/score/i.test(x)) - Number(!/score/i.test(y)) || x.length - y.length,
        )
        .slice(0, 6),
    [a.data],
  );
  if (!a.data) return <Loading what="Loading grader output" />;
  if (!jsons.length)
    return (
      <Empty title="No grader output">
        The verify run wrote no JSON result.{" "}
        <Link href={`${runPath(run.id)}?tab=logs`}>Logs →</Link>
      </Empty>
    );
  return (
    <div className="page-pad col" style={{ gap: 16 }}>
      {jsons.map((p) => (
        <GraderFile key={p} run={run} path={p} />
      ))}
    </div>
  );
}

function GraderFile({ run, path }: { run: Run; path: string }) {
  const t = useText(run.id, path);
  const parsed = useMemo(() => {
    try {
      return t.data ? (JSON.parse(t.data) as unknown) : null;
    } catch {
      return null;
    }
  }, [t.data]);
  const scored = itemsOf(parsed);
  return (
    <section className="card">
      <div className="card-h">
        <span className="mono">{path}</span>
        {scored && scored.total !== undefined && (
          <span className="sub">total {String(scored.total)}</span>
        )}
      </div>
      {t.data == null ? (
        <div className="card-b">{t.error ?? <Loading />}</div>
      ) : scored ? (
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>#</th>
              <th>Criterion</th>
              <th className="r" style={{ width: 70 }}>
                Weight
              </th>
              <th className="r" style={{ width: 70 }}>
                Score
              </th>
              <th>Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {scored.items.map((it, i) => (
              <tr key={String(i)} style={{ verticalAlign: "top" }}>
                <td className="faint num">{String(it.index ?? i)}</td>
                <td style={{ whiteSpace: "normal", maxWidth: 380 }}>
                  {it.type && <span className="chip mono">{it.type}</span>} {it.content}
                </td>
                <td className="r num muted">{it.weight ?? "—"}</td>
                <td className="r num">
                  <b>{it.score ?? "—"}</b>
                </td>
                <td className="muted" style={{ whiteSpace: "normal" }}>
                  <Reasoning text={it.reasoning ?? ""} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <pre className="card-b mono" style={{ maxHeight: 420, overflow: "auto", margin: 0 }}>
          {parsed ? JSON.stringify(parsed, null, 2) : t.data}
        </pre>
      )}
    </section>
  );
}

function Reasoning({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= 320) return <>{text}</>;
  return (
    <>
      {open ? text : `${text.slice(0, 320)}… `}
      <button type="button" className="btn ghost sm" onClick={() => setOpen(!open)}>
        {open ? "less" : "more"}
      </button>
    </>
  );
}
