import { IconSearch } from "./icons.tsx";

export interface MetricView {
  filter: string;
  smoothing: number;
  logY: boolean;
}

export function MetricControls({
  view,
  set,
  children,
}: {
  view: MetricView;
  set: (v: Partial<MetricView>) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="toolbar">
      <div className="search" style={{ width: 240 }}>
        <IconSearch size={14} />
        <input
          className="input"
          placeholder="Filter metrics (regex)…"
          value={view.filter}
          onChange={(e) => set({ filter: e.target.value })}
        />
      </div>
      <label
        className="row muted"
        style={{ gap: 8, fontSize: 12 }}
        title="Exponential moving average; the raw curve stays visible, faint"
      >
        Smoothing
        <input
          type="range"
          min={0}
          max={0.99}
          step={0.01}
          value={view.smoothing}
          onChange={(e) => set({ smoothing: Number(e.target.value) })}
          style={{ width: 120 }}
        />
        <span className="mono num" style={{ width: 30 }}>
          {view.smoothing.toFixed(2)}
        </span>
      </label>
      <button
        type="button"
        className={`btn sm${view.logY ? " on" : ""}`}
        onClick={() => set({ logY: !view.logY })}
      >
        log y
      </button>
      {children}
      <div className="spacer" />
      <span className="faint" style={{ fontSize: 12 }}>
        drag to zoom · double-click to reset · cursor is synced across charts
      </span>
    </div>
  );
}

export function keyMatcher(filter: string): (k: string) => boolean {
  if (!filter) return () => true;
  try {
    const re = new RegExp(filter, "i");
    return (k) => re.test(k);
  } catch {
    const f = filter.toLowerCase();
    return (k) => k.toLowerCase().includes(f);
  }
}

/** Group keys by their prefix before the first "/" (e.g. train/loss → train). */
export function sections(keys: string[]): [string, string[]][] {
  const m = new Map<string, string[]>();
  for (const k of keys) {
    const s = k.includes("/") ? (k.split("/")[0] as string) : "";
    m.set(s, [...(m.get(s) ?? []), k]);
  }
  return [...m.entries()].sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
}
