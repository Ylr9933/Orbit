import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  IconBot,
  IconChevron,
  IconChevronDown,
  IconCompare,
  IconFlask,
  IconGit,
  IconLayers,
  IconSearch,
  IconX,
} from "../components/icons.tsx";
import { TopBar } from "../components/TopBar.tsx";
import {
  ConfirmDialog,
  Empty,
  Kbd,
  Link,
  Loading,
  Params,
  StateBadge,
  stateColor,
  toast,
  useNow,
} from "../components/ui.tsx";
import { api, type BenchJobList, type Run, type RunState, type Trial } from "../lib/api.ts";
import {
  ago,
  dateTime,
  duration,
  fmtScore,
  harnessLabel,
  isActive,
  runDuration,
  runPath,
  runTitle,
  STATE_LABEL,
  STATES,
  trialPath,
} from "../lib/format.ts";
import { overlayOpen, useHotkeys } from "../lib/hotkeys.ts";
import { navigate, onLinkClick, setQuery, useLocation } from "../lib/router.ts";
import { useRuns, useRunsState } from "../lib/runs-store.ts";
import { useAsync } from "../lib/use.ts";

type Job = BenchJobList["jobs"][number];
const KINDS = ["all", "experiments", "bench"] as const;
type Kind = (typeof KINDS)[number];
const KIND_LABEL: Record<Kind, string> = {
  all: "All",
  experiments: "Experiments",
  bench: "Benchmarks",
};

type Entry =
  | { kind: "group"; name: string; runs: Run[]; key: string }
  | { kind: "run"; run: Run; inGroup: boolean; key: string };

function matches(r: Run, terms: string[]): boolean {
  if (!terms.length) return true;
  const hay = [
    r.id,
    r.spec.name,
    r.spec.group,
    r.spec.command.join(" "),
    r.spec.image,
    r.reason,
    r.note,
    r.code?.branch,
    r.code?.commit?.slice(0, 12),
    ...Object.entries(r.spec.params).map(([k, v]) => `${k}=${v}`),
    ...Object.entries(r.spec.tags).map(([k, v]) => `${k}=${v}`),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return terms.every((t) => hay.includes(t));
}

export function Runs() {
  const runs = useRuns();
  const { loaded, error } = useRunsState();
  const loc = useLocation();
  const q = loc.query.get("q") ?? "";
  const stateParam = loc.query.get("state") ?? "";
  const stateFilter = useMemo(
    () => stateParam.split(",").filter(Boolean) as RunState[],
    [stateParam],
  );
  const flat = loc.query.get("flat") === "1";
  const kind = (
    KINDS.includes(loc.query.get("kind") as Kind) ? loc.query.get("kind") : "all"
  ) as Kind;
  const jobs = useAsync(() => api.benchJobs(), [], { poll: true, pollMs: 10_000 });
  const jobByGroup = useMemo(
    () => new Map((jobs.data ?? []).map((j) => [`bench-${j.id}`, j])),
    [jobs.data],
  );
  const isBench = useCallback(
    (r: Run) => Boolean(r.spec.group && (jobByGroup.has(r.spec.group) || r.spec.tags.bench)),
    [jobByGroup],
  );
  const [deleting, setDeleting] = useState<string[] | null>(null);
  const [deletingJob, setDeletingJob] = useState<Job | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cursor, setCursor] = useState(0);
  const search = useRef<HTMLInputElement>(null);
  const anyActive = runs.some((r) => isActive(r.state));
  const now = useNow(1000, anyActive);

  const terms = useMemo(() => q.toLowerCase().split(/\s+/).filter(Boolean), [q]);
  const visible = useMemo(
    () =>
      runs.filter(
        (r) =>
          (stateFilter.length ? stateFilter.includes(r.state) : true) &&
          (kind === "all" || (kind === "bench") === isBench(r)) &&
          (matches(r, terms) || matchesJob(jobByGroup.get(r.spec.group ?? ""), terms)),
      ),
    [runs, stateFilter, terms, kind, isBench, jobByGroup],
  );

  const counts = useMemo(() => {
    const c: Partial<Record<RunState, number>> = {};
    for (const r of runs.filter((r) => matches(r, terms))) c[r.state] = (c[r.state] ?? 0) + 1;
    return c;
  }, [runs, terms]);

  const isExpanded = useCallback(
    (name: string, list: Run[]) =>
      open.has(name) ||
      (!closed.has(name) && (list.some((r) => isActive(r.state)) || terms.length > 0)),
    [open, closed, terms.length],
  );

  // Group runs by spec.group; a group sits where its newest run would be.
  const entries = useMemo<Entry[]>(() => {
    const out: Entry[] = [];
    const seen = new Map<string, Run[]>();
    for (const r of visible) {
      const g = !flat && r.spec.group;
      if (!g) {
        out.push({ kind: "run", run: r, inGroup: false, key: r.id });
        continue;
      }
      let list = seen.get(g);
      if (!list) {
        list = [];
        seen.set(g, list);
        out.push({ kind: "group", name: g, runs: list, key: `g:${g}` });
      }
      list.push(r);
    }
    const rows: Entry[] = [];
    for (const e of out) {
      rows.push(e);
      if (e.kind !== "group") continue;
      if (isExpanded(e.name, e.runs) && !jobByGroup.has(e.name))
        for (const r of [...e.runs].sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1)))
          rows.push({ kind: "run", run: r, inGroup: true, key: r.id });
    }
    return rows;
  }, [visible, flat, isExpanded, jobByGroup]);

  const toggleGroup = (name: string, list: Run[]) => {
    const exp = isExpanded(name, list);
    setOpen((s) => {
      const n = new Set(s);
      if (exp) n.delete(name);
      else n.add(name);
      return n;
    });
    setClosed((s) => {
      const n = new Set(s);
      if (exp) n.add(name);
      else n.delete(name);
      return n;
    });
  };

  const toggleSel = (ids: string[]) =>
    setSelected((s) => {
      const n = new Set(s);
      const all = ids.every((id) => n.has(id));
      for (const id of ids) {
        if (all) n.delete(id);
        else n.add(id);
      }
      return n;
    });

  useEffect(() => {
    if (cursor >= entries.length) setCursor(Math.max(0, entries.length - 1));
  }, [entries.length, cursor]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll whenever the cursor moves
  useEffect(() => {
    document.querySelector("tr.cursor")?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const current = entries[cursor];
  const compareHref = `/compare?ids=${[...selected].map(encodeURIComponent).join(",")}`;
  useHotkeys({
    j: () => setCursor((c) => Math.min(c + 1, entries.length - 1)),
    k: () => setCursor((c) => Math.max(c - 1, 0)),
    ArrowDown: () => setCursor((c) => Math.min(c + 1, entries.length - 1)),
    ArrowUp: () => setCursor((c) => Math.max(c - 1, 0)),
    Enter: () => open_(current),
    o: () => open_(current),
    x: () =>
      current &&
      toggleSel(current.kind === "run" ? [current.run.id] : current.runs.map((r) => r.id)),
    c: () => selected.size && navigate(compareHref),
    "/": () => search.current?.focus(),
    Escape: () => {
      if (!overlayOpen()) setSelected(new Set());
    },
  });

  function open_(e: Entry | undefined) {
    if (!e) return;
    if (e.kind === "run") navigate(`${runPath(e.run.id)}`);
    else toggleGroup(e.name, e.runs);
  }

  const setStates = (s: RunState[]) => setQuery({ state: s.join(",") || null });

  return (
    <>
      <TopBar crumbs={[{ label: "Runs" }]}>
        <div className="search" style={{ width: 340 }}>
          <IconSearch size={14} />
          <input
            ref={search}
            className="input"
            placeholder="Filter by name, id, group, param, tag, branch…"
            value={q}
            onChange={(e) => setQuery({ q: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Escape" || e.key === "Enter") e.currentTarget.blur();
            }}
          />
          {!q && <Kbd>/</Kbd>}
        </div>
      </TopBar>
      <div className="toolbar">
        <div className="filters">
          <button
            type="button"
            className={`fchip${stateFilter.length ? "" : " on"}`}
            onClick={() => setStates([])}
          >
            All <span className="n">{Object.values(counts).reduce((a, b) => a + b, 0)}</span>
          </button>
          {STATES.filter((s) => counts[s]).map((s) => {
            const on = stateFilter.includes(s);
            return (
              <button
                type="button"
                key={s}
                className={`fchip${on ? " on" : ""}`}
                onClick={(e) =>
                  setStates(
                    e.shiftKey || e.metaKey || e.ctrlKey
                      ? on
                        ? stateFilter.filter((x) => x !== s)
                        : [...stateFilter, s]
                      : on && stateFilter.length === 1
                        ? []
                        : [s],
                  )
                }
                title="Click to filter; shift-click to combine"
              >
                <span className="dot" style={{ "--c": stateColor(s) } as React.CSSProperties} />
                {STATE_LABEL[s]} <span className="n">{counts[s]}</span>
              </button>
            );
          })}
        </div>
        <div className="spacer" />
        <div className="seg" title="Kind of runs">
          {KINDS.map((k) => (
            <button
              type="button"
              key={k}
              className={kind === k ? "on" : ""}
              onClick={() => setQuery({ kind: k === "all" ? null : k })}
            >
              {k === "bench" && <IconFlask size={12} />} {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <div className="seg">
          <button
            type="button"
            className={flat ? "" : "on"}
            onClick={() => setQuery({ flat: null })}
          >
            Grouped
          </button>
          <button
            type="button"
            className={flat ? "on" : ""}
            onClick={() => setQuery({ flat: "1" })}
          >
            Flat
          </button>
        </div>
      </div>
      <div className="page">
        {!loaded ? (
          <Loading what="Loading runs" />
        ) : error ? (
          <Empty title="Could not load runs">{error}</Empty>
        ) : runs.length === 0 ? (
          <Empty title="No runs yet" icon={<IconLayers size={32} />}>
            <p>Ask your agent to launch an experiment, or run one yourself:</p>
            <p>
              <code>orbit run --gpus 1 --image python:3.12 -- python train.py</code>
            </p>
          </Empty>
        ) : entries.length === 0 ? (
          <Empty title="No runs match these filters" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 34 }} />
                <th style={{ width: 120 }}>State</th>
                <th>Run</th>
                <th>Params</th>
                <th>Resources</th>
                <th>Agent</th>
                <th>Code</th>
                <th>Created</th>
                <th className="r">Duration</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) =>
                e.kind === "group" && jobByGroup.has(e.name) ? (
                  <JobRow
                    key={e.key}
                    job={jobByGroup.get(e.name) as Job}
                    runs={e.runs}
                    expanded={isExpanded(e.name, e.runs)}
                    cursor={i === cursor}
                    selected={e.runs.every((r) => selected.has(r.id))}
                    onToggle={() => toggleGroup(e.name, e.runs)}
                    onSelect={() => toggleSel(e.runs.map((r) => r.id))}
                    onHover={() => setCursor(i)}
                    now={now}
                  />
                ) : e.kind === "group" ? (
                  <GroupRow
                    key={e.key}
                    name={e.name}
                    runs={e.runs}
                    expanded={isExpanded(e.name, e.runs)}
                    cursor={i === cursor}
                    selected={e.runs.every((r) => selected.has(r.id))}
                    onToggle={() => toggleGroup(e.name, e.runs)}
                    onSelect={() => toggleSel(e.runs.map((r) => r.id))}
                    onHover={() => setCursor(i)}
                    now={now}
                  />
                ) : (
                  <RunRow
                    key={e.key}
                    run={e.run}
                    inGroup={e.inGroup}
                    cursor={i === cursor}
                    selected={selected.has(e.run.id)}
                    onSelect={() => toggleSel([e.run.id])}
                    onHover={() => setCursor(i)}
                    now={now}
                  />
                ),
              )}
            </tbody>
          </table>
        )}
        {selected.size > 0 && (
          <div className="selbar">
            <b>{selected.size}</b> selected
            <Link className="btn primary sm" href={compareHref}>
              <IconCompare size={13} /> Compare <Kbd>c</Kbd>
            </Link>
            <CancelSelected ids={[...selected]} runs={runs} />
            <DeleteSelected
              ids={[...selected]}
              runs={runs}
              isBench={isBench}
              jobs={[...jobByGroup.values()]}
              onDelete={(ids) => setDeleting(ids)}
              onDeleteJob={(job) => setDeletingJob(job)}
            />
            <button
              type="button"
              className="btn ghost sm icon"
              onClick={() => setSelected(new Set())}
              title="Clear (Esc)"
            >
              <IconX size={13} />
            </button>
          </div>
        )}
      </div>
      {deletingJob && (
        <ConfirmDialog
          title={`Delete bench job ${deletingJob.spec.name ?? deletingJob.id}`}
          expected={deletingJob.id}
          action="Delete this job"
          onClose={() => setDeletingJob(null)}
          onConfirm={async () => {
            const r = await api.benchDeleteJob(deletingJob.id);
            setSelected(new Set());
            jobs.reload();
            toast(
              `Deleted job and ${r.deleted.length} run(s)${r.leftovers.length ? `; ${r.leftovers.length} folder(s) left on disk` : ""}`,
            );
          }}
        >
          <p>
            This deletes the job <b>{deletingJob.spec.name ?? deletingJob.id}</b> (
            {deletingJob.spec.benchmark}), its trials and all of their solve and verify runs: logs,
            outputs, reports, Agent sessions and scores.
          </p>
        </ConfirmDialog>
      )}
      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.length} run${deleting.length > 1 ? "s" : ""}`}
          expected={
            deleting.length === 1 ? (deleting[0] as string) : `delete ${deleting.length} runs`
          }
          action={`Delete ${deleting.length} run${deleting.length > 1 ? "s" : ""}`}
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            const r = await api.deleteRuns(deleting);
            setSelected(new Set());
            toast(
              `Deleted ${r.deleted.length} run(s)${r.leftovers.length ? `; ${r.leftovers.length} folder(s) left on disk` : ""}`,
            );
          }}
        >
          <p>
            Their records, logs, metrics, outputs, code snapshots and Agent sessions are removed
            from this machine.
          </p>
          <ul
            className="mono faint"
            style={{ margin: 0, paddingLeft: 18, maxHeight: 140, overflow: "auto" }}
          >
            {deleting.slice(0, 20).map((id) => (
              <li key={id}>{id}</li>
            ))}
            {deleting.length > 20 && <li>… {deleting.length - 20} more</li>}
          </ul>
        </ConfirmDialog>
      )}
    </>
  );
}

function matchesJob(job: Job | undefined, terms: string[]): boolean {
  if (!job || !terms.length) return false;
  const hay = [job.id, job.spec.name, job.spec.benchmark, ...job.spec.methods.map((m) => m.name)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return terms.every((t) => hay.includes(t));
}

/**
 * Finished runs outside bench jobs are deleted as runs; a bench job only as a whole, when every
 * run of it is selected and the job is not running. Anything else says why it is left out.
 */
function DeleteSelected(props: {
  ids: string[];
  runs: Run[];
  isBench: (r: Run) => boolean;
  jobs: Job[];
  onDelete: (ids: string[]) => void;
  onDeleteJob: (job: Job) => void;
}) {
  const sel = new Set(props.ids);
  const chosen = props.runs.filter((r) => sel.has(r.id));
  const ok = chosen.filter((r) => !isActive(r.state) && r.cleanup === "done" && !props.isBench(r));
  const jobRuns = (j: Job) => props.runs.filter((r) => r.spec.group === `bench-${j.id}`);
  const touched = props.jobs.filter((j) => jobRuns(j).some((r) => sel.has(r.id)));
  const whole = touched.filter((j) => jobRuns(j).every((r) => sel.has(r.id)));
  const partial = touched.length - whole.length;
  const skipped = chosen.filter((r) => !props.isBench(r)).length - ok.length;
  return (
    <>
      {ok.length > 0 && (
        <button
          type="button"
          className="btn danger sm"
          onClick={() => props.onDelete(ok.map((r) => r.id))}
          title={
            skipped ? `${skipped} selected run(s) are still active or not cleaned up` : undefined
          }
        >
          Delete {ok.length} run{ok.length > 1 ? "s" : ""}
          {skipped ? ` (${skipped} skipped)` : ""}
        </button>
      )}
      {whole.length === 1 && (
        <button
          type="button"
          className="btn danger sm"
          disabled={whole[0]?.state === "running"}
          title={whole[0]?.state === "running" ? "Cancel the job before deleting it" : undefined}
          onClick={() => props.onDeleteJob(whole[0] as Job)}
        >
          Delete job
        </button>
      )}
      {(whole.length > 1 || partial > 0) && (
        <span className="faint" style={{ fontSize: 12 }}>
          {whole.length > 1
            ? "Select one bench job at a time to delete it"
            : "Runs of a bench job are deleted with the whole job: select its row"}
        </span>
      )}
    </>
  );
}

function CancelSelected({ ids, runs }: { ids: string[]; runs: Run[] }) {
  const active = runs.filter((r) => ids.includes(r.id) && isActive(r.state));
  if (!active.length) return null;
  return (
    <button
      type="button"
      className="btn danger sm"
      onClick={async () => {
        if (!confirm(`Cancel ${active.length} active run(s)?`)) return;
        const res = await Promise.allSettled(active.map((r) => api.cancel(r.id)));
        const failed = res.filter((x) => x.status === "rejected").length;
        if (failed) toast(`${failed} of ${active.length} cancel request(s) failed`);
      }}
    >
      Cancel {active.length} active
    </button>
  );
}

function Resources({ run }: { run: Run }) {
  const r = run.spec.resources;
  return (
    <span className="muted num">
      {r.gpus ? (
        <b style={{ color: "var(--text)", fontWeight: 500 }}>{r.gpus}× GPU</b>
      ) : (
        <span className="faint">CPU</span>
      )}
      <span className="faint">
        {" "}
        · {r.cpus}c · {r.memGB}G
      </span>
    </span>
  );
}

function AgentCell({ run }: { run: Run }) {
  const a = run.spec.agent;
  if (!a) return <span className="faint">—</span>;
  return (
    <span className="row muted" style={{ gap: 5 }} title={a.sessionId ?? "session not identified"}>
      <IconBot size={13} />
      {harnessLabel(a.harness)}
    </span>
  );
}

function CodeCell({ run }: { run: Run }) {
  const c = run.code;
  if (!c) return <span className="faint">—</span>;
  return (
    <span
      className="row mono muted"
      style={{ gap: 5 }}
      title={`${c.branch ?? "detached"} @ ${c.commit ?? "no commit"}`}
    >
      <IconGit size={13} />
      {c.commit?.slice(0, 7) ?? "none"}
      {c.dirty && (
        <span
          className="chip warn mono"
          style={{ height: 18, padding: "0 6px" }}
          title={c.changedFiles.join("\n")}
        >
          +{c.changedFiles.length}
        </span>
      )}
    </span>
  );
}

function RunRow(props: {
  run: Run;
  inGroup: boolean;
  cursor: boolean;
  selected: boolean;
  onSelect: () => void;
  onHover: () => void;
  now: number;
}) {
  const { run, inGroup } = props;
  const cls = ["click", props.cursor && "cursor", props.selected && "sel"]
    .filter(Boolean)
    .join(" ");
  return (
    <tr className={cls} onClick={() => navigate(runPath(run.id))} onMouseMove={props.onHover}>
      <td onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="check"
          checked={props.selected}
          onChange={props.onSelect}
        />
      </td>
      <td>
        <StateBadge state={run.state} />
      </td>
      <td style={{ maxWidth: 440 }}>
        <div className="row" style={{ gap: 8, paddingLeft: inGroup ? 18 : 0 }}>
          <Link
            href={runPath(run.id)}
            className="ellipsis"
            style={{ color: "var(--text)", fontWeight: 500 }}
            onClick={(e) => {
              e.stopPropagation();
              onLinkClick(e);
            }}
          >
            {runTitle(run)}
          </Link>
          <span className="faint mono ellipsis" style={{ fontSize: 11 }}>
            {run.id}
          </span>
          {run.cleanup === "failed" && <span className="chip bad">cleanup failed</span>}
          {run.note && (
            <span className="chip" title={run.note}>
              note
            </span>
          )}
        </div>
        {run.state === "queued" && run.reason && (
          <div
            className="faint"
            style={{
              fontSize: 11.5,
              paddingLeft: inGroup ? 18 : 0,
              lineHeight: 1.2,
              marginTop: -4,
              marginBottom: 4,
            }}
          >
            {run.reason}
          </div>
        )}
      </td>
      <td>
        <Params params={run.spec.params} />
      </td>
      <td>
        <Resources run={run} />
      </td>
      <td>
        <AgentCell run={run} />
      </td>
      <td>
        <CodeCell run={run} />
      </td>
      <td className="muted" title={dateTime(run.createdAt)}>
        {ago(run.createdAt, props.now)}
      </td>
      <td className="r num muted">{duration(runDuration(run, props.now))}</td>
    </tr>
  );
}

function GroupRow(props: {
  name: string;
  runs: Run[];
  expanded: boolean;
  cursor: boolean;
  selected: boolean;
  onToggle: () => void;
  onSelect: () => void;
  onHover: () => void;
  now: number;
}) {
  const { runs } = props;
  const byState = STATES.map((s) => [s, runs.filter((r) => r.state === s).length] as const).filter(
    ([, n]) => n,
  );
  const keys = [...new Set(runs.flatMap((r) => Object.keys(r.spec.params)))];
  const varying = keys.filter((k) => new Set(runs.map((r) => r.spec.params[k])).size > 1);
  const starts = runs
    .map((r) => r.startedAt)
    .filter(Boolean)
    .map((s) => Date.parse(s as string));
  const ends = runs.map((r) =>
    r.endedAt ? Date.parse(r.endedAt) : isActive(r.state) ? props.now : Number.NaN,
  );
  const span = starts.length
    ? Math.max(...ends.filter(Number.isFinite)) - Math.min(...starts)
    : null;
  const newest = runs[0];
  const cls = ["click", "group-row", props.cursor && "cursor", props.selected && "sel"]
    .filter(Boolean)
    .join(" ");
  return (
    <tr className={cls} onClick={props.onToggle} onMouseMove={props.onHover}>
      <td onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="check"
          checked={props.selected}
          onChange={props.onSelect}
        />
      </td>
      <td>
        <div
          className="row"
          style={{ gap: 6 }}
          title={byState.map(([s, n]) => `${n} ${STATE_LABEL[s]}`).join(", ")}
        >
          <div className="stackbar">
            {byState.map(([s, n]) => (
              <span
                key={s}
                style={
                  {
                    "--c": stateColor(s),
                    width: `${(n / runs.length) * 100}%`,
                  } as React.CSSProperties
                }
              />
            ))}
          </div>
        </div>
      </td>
      <td>
        <div className="row" style={{ gap: 6 }}>
          {props.expanded ? <IconChevronDown size={14} /> : <IconChevron size={14} />}
          <IconLayers size={14} style={{ color: "var(--text-3)" }} />
          <span>{props.name}</span>
          <span className="chip">{runs.length} runs</span>
          {byState
            .filter(([s]) => s === "failed" || s === "running" || s === "queued")
            .map(([s, n]) => (
              <span
                key={s}
                className="faint"
                style={{ color: stateColor(s), fontWeight: 400, fontSize: 12 }}
              >
                {n} {STATE_LABEL[s].toLowerCase()}
              </span>
            ))}
        </div>
      </td>
      <td>
        {varying.length > 0 && (
          <span className="params">
            {varying.map((k) => (
              <span key={k} className="param">
                <i>{k}</i> ×{new Set(runs.map((r) => r.spec.params[k])).size}
              </span>
            ))}
          </span>
        )}
      </td>
      <td className="muted num">
        {runs.reduce((a, r) => a + r.spec.resources.gpus, 0) || <span className="faint">—</span>}
        {runs.some((r) => r.spec.resources.gpus) && <span className="faint"> GPU total</span>}
      </td>
      <td>{newest && <AgentCell run={newest} />}</td>
      <td>{newest && <CodeCell run={newest} />}</td>
      <td className="muted">{ago(newest?.createdAt, props.now)}</td>
      <td className="r num muted">
        <Link
          href={`/compare?group=${encodeURIComponent(props.name)}`}
          className="btn sm"
          onClick={(e) => {
            e.stopPropagation();
            onLinkClick(e);
          }}
          style={{ marginRight: 8 }}
        >
          <IconCompare size={12} /> Compare
        </Link>
        {duration(span)}
      </td>
    </tr>
  );
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);

/** A bench job in the run list: progress and method means; expands to its trials. */
function JobRow(props: {
  job: Job;
  runs: Run[];
  expanded: boolean;
  cursor: boolean;
  selected: boolean;
  onToggle: () => void;
  onSelect: () => void;
  onHover: () => void;
  now: number;
}) {
  const { job, runs } = props;
  const trials = job.summary.reduce((a, s) => a + s.trials, 0);
  const pending = job.summary.reduce((a, s) => a + s.pending, 0);
  const done = trials - pending;
  const starts = runs
    .map((r) => r.startedAt)
    .filter(Boolean)
    .map((t) => Date.parse(t as string));
  const end = job.endedAt ? Date.parse(job.endedAt) : props.now;
  const cls = ["click", "group-row", "job-row", props.cursor && "cursor", props.selected && "sel"]
    .filter(Boolean)
    .join(" ");
  return (
    <>
      <tr className={cls} onClick={props.onToggle} onMouseMove={props.onHover}>
        <td onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            className="check"
            checked={props.selected}
            onChange={props.onSelect}
          />
        </td>
        <td>
          <div className="row" style={{ gap: 6 }} title={`${done}/${trials} trials done`}>
            <div className="stackbar">
              <span
                style={
                  {
                    "--c": "var(--st-succeeded)",
                    width: `${(100 * done) / Math.max(1, trials)}%`,
                  } as React.CSSProperties
                }
              />
              <span
                style={
                  {
                    "--c": job.state === "running" ? "var(--st-running)" : "var(--st-cancelled)",
                    width: `${(100 * pending) / Math.max(1, trials)}%`,
                  } as React.CSSProperties
                }
              />
            </div>
          </div>
        </td>
        <td style={{ maxWidth: 520 }}>
          <div className="row" style={{ gap: 6 }}>
            {props.expanded ? <IconChevronDown size={14} /> : <IconChevron size={14} />}
            <IconFlask size={14} style={{ color: "var(--accent)" }} />
            <Link
              href={`/bench/${encodeURIComponent(job.id)}`}
              className="ellipsis"
              style={{ color: "var(--text)", fontWeight: 500 }}
              onClick={(e) => {
                e.stopPropagation();
                onLinkClick(e);
              }}
            >
              {job.spec.name ?? job.id}
            </Link>
            <span className="chip mono">{job.spec.benchmark}</span>
            <span className="chip">
              {done}/{trials} trials
            </span>
            {job.state !== "done" && <span className="faint">{job.state}</span>}
          </div>
        </td>
        <td colSpan={3}>
          <span className="params">
            {job.summary.map((s) => (
              <span
                key={s.method}
                className="param"
                title={`${s.valid} valid · ${s.invalid} invalid · ${s.unknown} unknown`}
              >
                <i>{s.method}</i> {pct(s.meanPct)}
                {s.invalid + s.unknown > 0 && (
                  <span className="faint"> ({s.invalid + s.unknown} not valid)</span>
                )}
              </span>
            ))}
          </span>
        </td>
        <td>{runs[0] && <AgentCell run={runs[0]} />}</td>
        <td className="muted" title={dateTime(job.createdAt)}>
          {ago(job.createdAt, props.now)}
        </td>
        <td className="r num muted">
          {duration(starts.length ? end - Math.min(...starts) : null)}
        </td>
      </tr>
      {props.expanded && <JobTrials job={job} runs={runs} now={props.now} />}
    </>
  );
}

/** One row per trial: task, method, solve → verify states, score, evaluation. */
function JobTrials({ job, runs, now }: { job: Job; runs: Run[]; now: number }) {
  const byId = useMemo(() => new Map(runs.map((r) => [r.id, r])), [runs]);
  const states = runs.map((r) => r.state).join(",");
  const d = useAsync(() => api.benchJob(job.id), [job.id, states]);
  if (!d.data)
    return (
      <tr>
        <td />
        <td colSpan={8} className="faint" style={{ paddingLeft: 40 }}>
          {d.error ?? "Loading trials…"}
        </td>
      </tr>
    );
  return (
    <>
      {d.data.trials.map((t) => (
        <TrialRow
          key={t.id}
          t={t}
          seeds={job.spec.seeds}
          solve={byId.get(t.solveRunId ?? "")}
          verify={byId.get(t.verifyRunId ?? "")}
          now={now}
        />
      ))}
    </>
  );
}

function PhaseDot({ run, label }: { run: Run | undefined; label: string }) {
  return (
    <span className="row" style={{ gap: 4 }} title={`${label}: ${run ? run.state : "not started"}`}>
      <span
        className="dot"
        style={
          { "--c": run ? stateColor(run.state) : "var(--border-strong)" } as React.CSSProperties
        }
      />
      <span className="faint" style={{ fontSize: 11 }}>
        {label}
      </span>
    </span>
  );
}

function TrialRow(props: { t: Trial; seeds: number; solve?: Run; verify?: Run; now: number }) {
  const { t, solve, verify } = props;
  const o = t.outcome;
  const href = trialPath(t.jobId, t.id);
  const ev = o?.evaluation;
  return (
    <tr className="click trial-row" onClick={() => navigate(href)}>
      <td />
      <td>
        <div className="row" style={{ gap: 8 }}>
          <PhaseDot run={solve} label="solve" />
          <PhaseDot run={verify} label="verify" />
        </div>
      </td>
      <td>
        <div className="row" style={{ gap: 8, paddingLeft: 18 }}>
          <Link
            href={href}
            className="mono"
            style={{ color: "var(--text)" }}
            onClick={(e) => {
              e.stopPropagation();
              onLinkClick(e);
            }}
          >
            {t.task}
          </Link>
          <span className="muted">{t.method}</span>
          {props.seeds > 1 && <span className="faint">#{t.seed}</span>}
        </div>
      </td>
      <td colSpan={3}>
        {o && o.score !== null && (
          <span className="num">
            <b>{fmtScore(o.score)}</b>
            <span className="faint"> / {fmtScore(o.maxScore)}</span>
          </span>
        )}{" "}
        {ev && (
          <span className={`chip ${ev === "valid" ? "good" : ev === "invalid" ? "bad" : "warn"}`}>
            {ev}
          </span>
        )}{" "}
        {(o?.issues ?? t.issues).length > 0 && (
          <span
            className="faint ellipsis"
            style={{ fontSize: 12 }}
            title={(o?.issues ?? t.issues).join("\n")}
          >
            {(o?.issues ?? t.issues)[0]}
          </span>
        )}
      </td>
      <td />
      <td className="muted">{ago(t.createdAt, props.now)}</td>
      <td className="r num muted">{duration(solve ? runDuration(solve, props.now) : null)}</td>
    </tr>
  );
}
