// Bench metric building blocks shared by the job, compare and trial pages: the metric switch (kept
// in the URL), heat-coloured score cells and mean ± 95% CI bars with an optional reference line.
// Values, aggregation and formatting come from `@zjunlp/orbit/metrics`, the daemon's own rules.
import {
  fmtCi,
  fmtMetric,
  goodness,
  type MetricDef,
  type MetricStat,
  primaryMetric,
} from "@zjunlp/orbit/metrics";
import type { Outcome } from "../lib/api.ts";
import { setQuery, useLocation } from "../lib/router.ts";
import { Link } from "./ui.tsx";

/** The metric picked with `?metric=`, else the primary one. */
export function useMetric(metrics: MetricDef[]): [MetricDef, (name: string) => void] {
  const loc = useLocation();
  const name = loc.query.get("metric");
  const m = metrics.find((x) => x.name === name) ?? primaryMetric(metrics);
  const primary = primaryMetric(metrics).name;
  return [m, (n) => setQuery({ metric: n === primary ? null : n })];
}

export function MetricSwitch({
  metrics,
  value,
  onChange,
}: {
  metrics: MetricDef[];
  value: MetricDef;
  onChange: (name: string) => void;
}) {
  if (metrics.length < 2) return null;
  return (
    <div className="seg" role="tablist" aria-label="Metric">
      {metrics.map((m) => (
        <button
          key={m.name}
          type="button"
          role="tab"
          aria-selected={m.name === value.name}
          className={m.name === value.name ? "on" : ""}
          title={m.description}
          onClick={() => onChange(m.name)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

/** One value in a matrix, coloured by where it lies in the metric's range (better = greener). */
export function ScoreCell({
  value,
  metric,
  evaluation,
  href,
  title,
  note,
}: {
  value: number | null;
  metric: MetricDef;
  evaluation: Outcome["evaluation"] | "pending";
  href?: string;
  title?: string;
  note?: string;
}) {
  const cls = evaluation === "valid" ? "" : evaluation;
  const text =
    evaluation === "pending" ? "…" : evaluation === "valid" ? fmtMetric(value, metric) : evaluation;
  const style = { "--p": goodness(value, metric) ?? 0 } as React.CSSProperties;
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

/** `72.5%` with `±3.2` in small type. */
export function StatValue({ s, metric }: { s: MetricStat | null | undefined; metric: MetricDef }) {
  const ci = fmtCi(s, metric);
  return (
    <span className="stat-value" title={ciTitle(s, metric)}>
      {fmtMetric(s?.mean, metric)}
      {ci && <small>{ci}</small>}
    </span>
  );
}

export function ciTitle(s: MetricStat | null | undefined, m: MetricDef): string | undefined {
  if (!s) return undefined;
  const ci = s.ci ? `95% CI ${fmtMetric(s.ci[0], m)} – ${fmtMetric(s.ci[1], m)}` : "no CI (1 task)";
  return `${ci} · ${s.tasks} task${s.tasks === 1 ? "" : "s"}, ${s.trials} trial${s.trials === 1 ? "" : "s"}`;
}

/** Axis of a set of bars: the metric's range, else what the values, CIs and reference span. */
function axis(stats: (MetricStat | null)[], m: MetricDef): [number, number] {
  if (m.range) return m.range;
  const xs = stats.flatMap((s) => (s ? [s.mean, ...(s.ci ?? [])] : []));
  if (m.reference !== undefined) xs.push(m.reference);
  const lo = Math.min(0, ...xs);
  const hi = Math.max(lo + 1e-9, ...xs);
  return [lo, hi + (hi - lo) * 0.05];
}

/** Leaderboard-style horizontal bars: mean, 95% CI whisker and the metric's reference line. */
export function CiBars({
  rows,
  metric,
}: {
  rows: { key: string; label: string; s: MetricStat | null; href?: string }[];
  metric: MetricDef;
}) {
  const [lo, hi] = axis(
    rows.map((r) => r.s),
    metric,
  );
  const at = (v: number) => `${(100 * (Math.min(hi, Math.max(lo, v)) - lo)) / (hi - lo)}%`;
  const ordered = [...rows].sort((a, b) => {
    if (!a.s || !b.s) return a.s ? -1 : b.s ? 1 : 0;
    return metric.higherIsBetter ? b.s.mean - a.s.mean : a.s.mean - b.s.mean;
  });
  return (
    <div className="cibars">
      {ordered.map((r, i) => (
        <div key={r.key} className="cibar">
          <span className="rank">{r.s ? i + 1 : "–"}</span>
          <span className="name mono ellipsis" title={r.label}>
            {r.href ? <Link href={r.href}>{r.label}</Link> : r.label}
          </span>
          <div className="track" title={ciTitle(r.s, metric)}>
            {r.s && <div className="fill" style={{ width: at(r.s.mean) }} />}
            {r.s?.ci && (
              <div
                className="whisker"
                style={{ left: at(r.s.ci[0]), width: `calc(${at(r.s.ci[1])} - ${at(r.s.ci[0])})` }}
              />
            )}
            {metric.reference !== undefined && (
              <div className="ref" style={{ left: at(metric.reference) }} />
            )}
          </div>
          <StatValue s={r.s} metric={metric} />
        </div>
      ))}
      {metric.reference !== undefined && (
        <div className="cibar-legend faint">
          <span className="ref-key" /> reference {fmtMetric(metric.reference, metric)}
          {" · "}whiskers: 95% CI clustered by task
        </div>
      )}
    </div>
  );
}
