import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  IconAlert,
  IconArrowDown,
  IconChevronDown,
  IconDownload,
  IconFilter,
  IconSearch,
  IconWrap,
} from "../../components/icons.tsx";
import { Empty, Kbd, Loading } from "../../components/ui.tsx";
import { api, logUrl, type Run } from "../../lib/api.ts";
import { bytes, isActive } from "../../lib/format.ts";
import { useHotkeys } from "../../lib/hotkeys.ts";
import { ansiSpans, type LogLine, toLines } from "../../lib/log.ts";
import { setHash, useLocation } from "../../lib/router.ts";

/** Load at most this much of a log into the browser; older bytes are available via download. */
const MAX_BYTES = 48 * 1024 * 1024;
const CHUNK = 2 * 1024 * 1024;

interface LogState {
  lines: LogLine[];
  /** Bytes after the last complete line; rendered as a trailing partial line. */
  partial: string;
  next: number;
  size: number;
  /** Byte offset where the loaded window starts (>0 when the head was skipped). */
  start: number;
  eof: boolean;
  loaded: boolean;
}

function useLog(run: Run) {
  const [st, setSt] = useState<LogState>({
    lines: [],
    partial: "",
    next: 0,
    size: 0,
    start: 0,
    eof: false,
    loaded: false,
  });
  const ref = useRef(st);
  ref.current = st;
  const busy = useRef(false);
  const active = isActive(run.state);

  const pull = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      let s = ref.current;
      // First fetch: learn the size; skip the head of very large logs.
      if (!s.loaded) {
        const probe = await api.logs(run.id, 0, 1);
        const start = probe.size > MAX_BYTES ? probe.size - MAX_BYTES : 0;
        s = { ...s, next: start, start, size: probe.size };
      }
      for (let i = 0; i < 64; i++) {
        const c = await api.logs(run.id, s.next, CHUNK);
        let text = s.partial + c.text;
        // When starting mid-file, drop the first (partial) line.
        if (s.start > 0 && s.next === s.start && s.lines.length === 0)
          text = text.slice(text.indexOf("\n") + 1);
        const cut = text.lastIndexOf("\n");
        const complete = cut >= 0 ? text.slice(0, cut + 1) : "";
        const partial = cut >= 0 ? text.slice(cut + 1) : text;
        const add = complete ? toLines(complete, s.lines.length + 1) : [];
        s = {
          ...s,
          lines: add.length ? s.lines.concat(add) : s.lines,
          partial,
          next: c.next,
          size: c.size,
          eof: c.eof,
          loaded: true,
        };
        setSt(s);
        if (c.next >= c.size) break;
      }
    } catch {
      // transient; next poll retries
    } finally {
      busy.current = false;
    }
  }, [run.id]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: pull again when the state changes
  useEffect(() => {
    void pull();
  }, [pull, run.state]);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void pull(), 1000);
    return () => clearInterval(t);
  }, [active, pull]);
  // After the run ends, keep pulling until the daemon reports EOF (logs are drained before cleanup).
  // biome-ignore lint/correctness/useExhaustiveDependencies: st.next re-arms the timer after each pull
  useEffect(() => {
    if (active || st.eof || !st.loaded) return;
    const t = setTimeout(() => void pull(), 800);
    return () => clearTimeout(t);
  }, [active, st.eof, st.loaded, st.next, pull]);

  const lines = useMemo(
    () => (st.partial ? st.lines.concat(toLines(st.partial, st.lines.length + 1)) : st.lines),
    [st.lines, st.partial],
  );
  return { ...st, lines };
}

function parseHash(h: string): [number, number] | null {
  const m = /^L(\d+)(?:-L?(\d+))?$/.exec(h);
  if (!m) return null;
  const a = Number(m[1]);
  const b = Number(m[2] ?? m[1]);
  return [Math.min(a, b), Math.max(a, b)];
}

export function LogsTab({ run }: { run: Run }) {
  const log = useLog(run);
  const loc = useLocation();
  const [q, setQ] = useState("");
  const [regex, setRegex] = useState(false);
  const [caseSens, setCaseSens] = useState(false);
  const [filter, setFilter] = useState(false);
  const [hideSys, setHideSys] = useState(false);
  const [wrap, setWrap] = useState(false);
  const [follow, setFollow] = useState(isActive(run.state));
  const [cur, setCur] = useState(0);
  const [seen, setSeen] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const range = parseHash(loc.hash);
  const jumpedErr = useRef(false);
  const jumpedHash = useRef(false);

  const re = useMemo(() => {
    if (!q) return null;
    try {
      return new RegExp(
        regex ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
        caseSens ? "g" : "gi",
      );
    } catch {
      return null;
    }
  }, [q, regex, caseSens]);
  const badRegex = Boolean(q) && !re;

  const matchLines = useMemo(() => {
    if (!re) return [];
    const out: number[] = [];
    for (const l of log.lines) {
      re.lastIndex = 0;
      if (re.test(l.plain)) out.push(l.n);
    }
    return out;
  }, [log.lines, re]);

  const shown = useMemo(() => {
    let ls = log.lines;
    if (hideSys) ls = ls.filter((l) => l.kind !== "sys");
    if (filter && re) {
      const set = new Set(matchLines);
      ls = ls.filter((l) => set.has(l.n));
    }
    return ls;
  }, [log.lines, hideSys, filter, re, matchLines]);

  const errLines = useMemo(
    () => log.lines.filter((l) => l.kind === "err").map((l) => l.n),
    [log.lines],
  );

  const v = useVirtualizer({
    count: shown.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 20,
    overscan: 30,
  });

  const indexOfLine = useCallback(
    (n: number) => {
      // shown is sorted by n; binary search
      let lo = 0;
      let hi = shown.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const x = (shown[mid] as LogLine).n;
        if (x === n) return mid;
        if (x < n) lo = mid + 1;
        else hi = mid - 1;
      }
      return Math.min(lo, shown.length - 1);
    },
    [shown],
  );

  const scrollToLine = useCallback(
    (n: number) => {
      setFollow(false);
      v.scrollToIndex(indexOfLine(n), { align: "center" });
    },
    [v, indexOfLine],
  );

  // Follow: stick to the bottom as lines arrive.
  useEffect(() => {
    if (follow && shown.length) {
      v.scrollToIndex(shown.length - 1, { align: "end" });
      setSeen(shown.length);
    }
  }, [follow, shown.length, v]);

  // Deep links: #L10-L20 and ?err=1 (from Overview).
  useEffect(() => {
    if (!log.loaded || jumpedHash.current) return;
    if (range && log.lines.length >= range[0]) {
      jumpedHash.current = true;
      scrollToLine(range[0]);
    }
  }, [log.loaded, log.lines.length, range, scrollToLine]);
  useEffect(() => {
    if (jumpedErr.current || !log.eof) return;
    if (new URLSearchParams(location.search).get("err") === "1") {
      jumpedErr.current = true;
      if (errLines[0]) {
        setHash(`L${errLines[0]}`);
        scrollToLine(errLines[0]);
      }
    }
  }, [log.eof, errLines, scrollToLine]);

  const gotoMatch = (i: number) => {
    if (!matchLines.length) return;
    const k = (i + matchLines.length) % matchLines.length;
    setCur(k);
    scrollToLine(matchLines[k] as number);
  };
  const jumpError = () => {
    if (!errLines.length) return;
    const after = errLines.find((n) => !range || n > range[0]) ?? (errLines[0] as number);
    setHash(`L${after}`);
    scrollToLine(after);
  };

  useHotkeys({
    "/": () => searchRef.current?.focus(),
    "mod+f": () => searchRef.current?.focus(),
    n: () => gotoMatch(cur + 1),
    "shift+N": () => gotoMatch(cur - 1),
    e: jumpError,
    f: () => setFollow((f) => !f),
    w: () => setWrap((w) => !w),
    G: () => setFollow(true),
  });

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
    if (atBottom !== follow) setFollow(atBottom);
    if (atBottom) setSeen(shown.length);
  };

  const onLineClick = (n: number, e: React.MouseEvent) => {
    if (e.shiftKey && range) setHash(`L${Math.min(range[0], n)}-L${Math.max(range[1], n)}`);
    else if (range && range[0] === n && range[1] === n) setHash("");
    else setHash(`L${n}`);
  };

  const running = isActive(run.state);
  // Only live output counts as "new"; a finished log loads all at once.
  const newLines = follow || !running ? 0 : Math.max(0, shown.length - seen);
  const curLine = matchLines[cur];

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="toolbar">
        <div className="search" style={{ width: 320 }}>
          <IconSearch size={14} />
          <input
            ref={searchRef}
            className="input mono"
            style={{ paddingRight: 70, borderColor: badRegex ? "var(--st-failed)" : undefined }}
            placeholder={regex ? "regex…" : "Search logs…"}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCur(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter")
                gotoMatch(e.shiftKey ? cur - 1 : cur + (matchLines[cur] === undefined ? 0 : 1));
              if (e.key === "Escape") e.currentTarget.blur();
            }}
          />
          <span className="faint mono" style={{ position: "absolute", right: 8, fontSize: 11 }}>
            {q ? (
              badRegex ? (
                "invalid"
              ) : (
                `${matchLines.length ? cur + 1 : 0}/${matchLines.length}`
              )
            ) : (
              <Kbd>/</Kbd>
            )}
          </span>
        </div>
        <div className="seg">
          <button
            type="button"
            className={regex ? "on" : ""}
            onClick={() => setRegex(!regex)}
            title="Regular expression"
          >
            .*
          </button>
          <button
            type="button"
            className={caseSens ? "on" : ""}
            onClick={() => setCaseSens(!caseSens)}
            title="Match case"
          >
            Aa
          </button>
        </div>
        <button
          type="button"
          className="btn sm icon"
          onClick={() => gotoMatch(cur - 1)}
          title="Previous match (N)"
          disabled={!matchLines.length}
        >
          <IconChevronDown size={14} style={{ transform: "rotate(180deg)" }} />
        </button>
        <button
          type="button"
          className="btn sm icon"
          onClick={() => gotoMatch(cur + 1)}
          title="Next match (n)"
          disabled={!matchLines.length}
        >
          <IconChevronDown size={14} />
        </button>
        <button
          type="button"
          className={`btn sm${filter ? " on" : ""}`}
          onClick={() => setFilter(!filter)}
          title="Show only matching lines"
          disabled={!re}
        >
          <IconFilter size={13} /> Only matches
        </button>
        <div className="spacer" />
        <button
          type="button"
          className="btn sm"
          onClick={jumpError}
          disabled={!errLines.length}
          title="Jump to next error-looking line (e)"
        >
          <IconAlert
            size={13}
            style={{ color: errLines.length ? "var(--st-failed)" : undefined }}
          />
          {errLines.length ? `${errLines.length} error lines` : "No errors"}
        </button>
        <button
          type="button"
          className={`btn sm${hideSys ? "" : " on"}`}
          onClick={() => setHideSys(!hideSys)}
          title="Show Orbit system lines"
        >
          [orbit]
        </button>
        <button
          type="button"
          className={`btn sm icon${wrap ? " on" : ""}`}
          onClick={() => setWrap(!wrap)}
          title="Wrap lines (w)"
        >
          <IconWrap size={14} />
        </button>
        <button
          type="button"
          className={`btn sm${follow ? " on" : ""}`}
          onClick={() => setFollow(!follow)}
          title="Follow output (f)"
        >
          <IconArrowDown size={13} /> Follow
        </button>
        <a className="btn sm icon" href={logUrl(run.id, true)} title="Download full log">
          <IconDownload size={14} />
        </a>
      </div>
      {log.start > 0 && (
        <div
          className="callout"
          style={{ borderRadius: 0, "--c": "var(--st-cancelled)" } as React.CSSProperties}
        >
          Showing the last {bytes(log.size - log.start)} of {bytes(log.size)}.{" "}
          <a href={logUrl(run.id, true)}>Download the full log</a>.
        </div>
      )}
      {!log.loaded ? (
        <Loading what="Loading logs" />
      ) : log.lines.length === 0 ? (
        <Empty
          title={
            run.state === "queued" ? "Waiting to start" : running ? "No output yet" : "No output"
          }
        >
          {run.state === "queued"
            ? run.reason
            : running
              ? "Lines appear here as the container writes them."
              : null}
        </Empty>
      ) : (
        <div ref={scroller} className={`logview${wrap ? " wrap" : ""}`} onScroll={onScroll}>
          <div
            style={{
              height: v.getTotalSize(),
              position: "relative",
              minWidth: "100%",
              width: wrap ? "100%" : "max-content",
            }}
          >
            {v.getVirtualItems().map((item) => {
              const l = shown[item.index] as LogLine;
              const hl = range && l.n >= range[0] && l.n <= range[1];
              return (
                <div
                  key={item.key}
                  data-index={item.index}
                  ref={wrap ? v.measureElement : undefined}
                  className={`logline ${l.kind}${hl ? " hl" : ""}`}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    transform: `translateY(${item.start}px)`,
                  }}
                >
                  <span className="ln" onClick={(e) => onLineClick(l.n, e)}>
                    {l.n}
                  </span>
                  <span className="tx">
                    <LineText line={l} re={re} current={l.n === curLine} />
                  </span>
                </div>
              );
            })}
          </div>
          {newLines > 0 && (
            <div className="follow-pill">
              <button type="button" className="btn primary sm" onClick={() => setFollow(true)}>
                <IconArrowDown size={13} /> {newLines} new lines
              </button>
            </div>
          )}
        </div>
      )}
      <div
        className="toolbar faint"
        style={{
          borderTop: "1px solid var(--border)",
          borderBottom: 0,
          padding: "4px 16px",
          fontSize: 11.5,
        }}
      >
        <span className="num">
          {log.lines.length.toLocaleString()} lines · {bytes(log.size)}
        </span>
        {filter && re && <span>· showing {shown.length.toLocaleString()} matching</span>}
        <div className="spacer" />
        {running ? (
          <span className="row" style={{ gap: 6 }}>
            <span
              className="dot pulse"
              style={{ "--c": "var(--st-running)" } as React.CSSProperties}
            />{" "}
            live
          </span>
        ) : log.eof ? (
          <span>complete</span>
        ) : (
          <span>collecting…</span>
        )}
        <span>
          click a line number to link it · shift-click for a range · <Kbd>n</Kbd> <Kbd>N</Kbd>{" "}
          <Kbd>e</Kbd> <Kbd>f</Kbd>
        </span>
      </div>
    </div>
  );
}

function LineText({ line, re, current }: { line: LogLine; re: RegExp | null; current: boolean }) {
  if (re) {
    re.lastIndex = 0;
    if (re.test(line.plain)) {
      re.lastIndex = 0;
      const parts: React.ReactNode[] = [];
      let last = 0;
      let k = 0;
      for (const m of line.plain.matchAll(re)) {
        if (m[0] === "") break;
        const i = m.index ?? 0;
        parts.push(line.plain.slice(last, i));
        parts.push(
          <mark key={k++} className={current && k === 1 ? "cur" : ""}>
            {m[0]}
          </mark>,
        );
        last = i + m[0].length;
      }
      parts.push(line.plain.slice(last));
      return <>{parts}</>;
    }
  }
  if (!line.raw.includes("\x1b")) return <>{line.raw || " "}</>;
  return (
    <>
      {ansiSpans(line.raw).map((s, i) => (
        <span
          key={String(i)}
          style={{
            color: s.fg,
            background: s.bg,
            fontWeight: s.bold ? 600 : undefined,
            opacity: s.dim ? 0.6 : undefined,
            fontStyle: s.italic ? "italic" : undefined,
            textDecoration: s.underline ? "underline" : undefined,
          }}
        >
          {s.text}
        </span>
      ))}
    </>
  );
}
