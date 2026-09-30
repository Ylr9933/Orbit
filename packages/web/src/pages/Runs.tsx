import { useEffect, useMemo, useRef, useState } from "react";
import {
  IconBot,
  IconChevron,
  IconChevronDown,
  IconCompare,
  IconGit,
  IconLayers,
  IconSearch,
  IconX,
} from "../components/icons.tsx";
import { TopBar } from "../components/TopBar.tsx";
import {
  Empty,
  Kbd,
  Link,
  Loading,
  Params,
  StateBadge,
  stateColor,
  useNow,
} from "../components/ui.tsx";
import { api, type Run, type RunState } from "../lib/api.ts";
import {
  ago,
  dateTime,
  duration,
  harnessLabel,
  isActive,
  runDuration,
  runTitle,
  STATE_LABEL,
  STATES,
} from "../lib/format.ts";
import { useHotkeys } from "../lib/hotkeys.ts";
import { navigate, setQuery, useLocation } from "../lib/router.ts";
import { useRuns, useRunsState } from "../lib/runs-store.ts";

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
        (r) => (stateFilter.length ? stateFilter.includes(r.state) : true) && matches(r, terms),
      ),
    [runs, stateFilter, terms],
  );

  const counts = useMemo(() => {
    const c: Partial<Record<RunState, number>> = {};
    for (const r of runs.filter((r) => matches(r, terms))) c[r.state] = (c[r.state] ?? 0) + 1;
    return c;
  }, [runs, terms]);

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
      const expanded =
        open.has(e.name) ||
        (!closed.has(e.name) && (e.runs.some((r) => isActive(r.state)) || terms.length > 0));
      if (expanded)
        for (const r of [...e.runs].sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1)))
          rows.push({ kind: "run", run: r, inGroup: true, key: r.id });
    }
    return rows;
  }, [visible, flat, open, closed, terms.length]);

  const isExpanded = (name: string, list: Run[]) =>
    open.has(name) ||
    (!closed.has(name) && (list.some((r) => isActive(r.state)) || terms.length > 0));

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
  const compareHref = `/compare?ids=${[...selected].join(",")}`;
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
    Escape: () => setSelected(new Set()),
  });

  function open_(e: Entry | undefined) {
    if (!e) return;
    if (e.kind === "run") navigate(`/runs/${e.run.id}`);
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
                    e.shiftKey || e.metaKey
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
                e.kind === "group" ? (
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
        await Promise.all(active.map((r) => api.cancel(r.id).catch(() => null)));
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
  const params = inGroup ? run.spec.params : run.spec.params;
  return (
    <tr className={cls} onClick={() => navigate(`/runs/${run.id}`)} onMouseMove={props.onHover}>
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
            href={`/runs/${run.id}`}
            className="ellipsis"
            style={{ color: "var(--text)", fontWeight: 500 }}
            onClick={(e) => {
              e.stopPropagation();
              if (!e.metaKey && !e.ctrlKey) {
                e.preventDefault();
                navigate(`/runs/${run.id}`);
              }
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
        <Params params={params} />
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
          title={byState.map(([s, n]) => `${n} ${s}`).join(", ")}
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
                {n} {s}
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
            e.preventDefault();
            navigate(`/compare?group=${encodeURIComponent(props.name)}`);
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
