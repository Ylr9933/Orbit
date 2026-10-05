// Bench metrics (design §7): what a trial value is, how valid trials aggregate and how values are shown.
// One implementation for the daemon, the CLI and the Web UI. No imports, so the Web bundle can use it
// at runtime (`@zjunlp/orbit/metrics`); the zod schema `MetricSpec` in index.ts has the same shape.
//
// Every metric is a mean: per task over its valid seeds first, then over tasks. Standard errors are
// clustered by task (the seeds of a task are not independent samples), and comparisons use paired
// per-task differences, following the usual practice of model evaluation reports.

export interface MetricDef {
  name: string;
  label: string;
  description?: string;
  /** Display only, e.g. `%`, `pts`, `$`, `s`. */
  unit?: string;
  /** Natural bounds, for the heat colour of cells and the scale of bars. */
  range?: [number, number];
  higherIsBetter: boolean;
  primary: boolean;
  /** A reference value (paper result, human baseline) drawn next to results. */
  reference?: number;
}

/** What a trial contributes: an outcome's score and its adapter metrics. */
export interface MetricSource {
  score: number | null;
  maxScore: number;
  metrics?: Record<string, number>;
}

export interface MetricStat {
  mean: number;
  /** Standard error clustered by task; null with fewer than two tasks. */
  se: number | null;
  /** 95% confidence interval (normal approximation); null without `se`. */
  ci: [number, number] | null;
  tasks: number;
  trials: number;
}

/** Built-in metric of every benchmark: the score as a percent of its maximum. */
export const SCORE = "score";
export const SCORE_METRIC: MetricDef = {
  name: SCORE,
  label: "Score",
  unit: "%",
  range: [0, 100],
  higherIsBetter: true,
  primary: true,
};

const Z95 = 1.959964;

/**
 * The metrics of a job from what its adapter declared: `score` first (a declaration named `score`
 * may change its label, description, unit, reference and whether it is primary, not its value or
 * range), then the rest in declared order. Exactly one is primary: the first declared primary, else
 * `score`. Idempotent.
 */
export function resolveMetrics(declared: readonly MetricDef[]): MetricDef[] {
  const own = declared.find((m) => m.name === SCORE);
  const score: MetricDef = {
    ...SCORE_METRIC,
    ...(own
      ? {
          label: own.label,
          description: own.description,
          unit: own.unit,
          reference: own.reference,
        }
      : {}),
    range: SCORE_METRIC.range,
    higherIsBetter: true,
  };
  const all = [score, ...declared.filter((m) => m.name !== SCORE)];
  const primary = declared.find((m) => m.primary)?.name ?? SCORE;
  return all.map((m) => ({ ...m, primary: m.name === primary }));
}

export const primaryMetric = (ms: readonly MetricDef[]): MetricDef =>
  ms.find((m) => m.primary) ?? ms[0] ?? SCORE_METRIC;

/** A trial's value of a metric; null when the trial has none. */
export function metricValue(o: MetricSource | null | undefined, name: string): number | null {
  if (!o) return null;
  if (name === SCORE)
    return o.score === null || o.maxScore <= 0 ? null : (100 * o.score) / o.maxScore;
  const v = o.metrics?.[name];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

const avg = (xs: readonly number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

function stat(means: readonly number[], trials: number): MetricStat | null {
  if (means.length === 0) return null;
  const mean = avg(means);
  const n = means.length;
  const se = n < 2 ? null : Math.sqrt(means.reduce((a, x) => a + (x - mean) ** 2, 0) / (n - 1) / n);
  return {
    mean,
    se,
    ci: se === null ? null : [mean - Z95 * se, mean + Z95 * se],
    tasks: n,
    trials,
  };
}

/** Per-task means of a metric over the given (valid) trials. */
export function taskMeans(
  trials: readonly { task: string; outcome: MetricSource | null }[],
  name: string,
): Map<string, { mean: number; n: number }> {
  const by = new Map<string, number[]>();
  for (const t of trials) {
    const v = metricValue(t.outcome, name);
    if (v === null) continue;
    const xs = by.get(t.task);
    if (xs) xs.push(v);
    else by.set(t.task, [v]);
  }
  return new Map([...by].map(([task, xs]) => [task, { mean: avg(xs), n: xs.length }]));
}

/** Mean over tasks of per-task means, restricted to `only` when given. */
export function aggregate(
  means: Map<string, { mean: number; n: number }>,
  only?: ReadonlySet<string>,
): MetricStat | null {
  const rows = [...means].filter(([task]) => !only || only.has(task)).map(([, r]) => r);
  return stat(
    rows.map((r) => r.mean),
    rows.reduce((a, r) => a + r.n, 0),
  );
}

/** Mean paired difference `b − a` over the tasks both have, with its clustered SE and CI. */
export function pairedDiff(
  a: Map<string, { mean: number }>,
  b: Map<string, { mean: number }>,
): MetricStat | null {
  const ds: number[] = [];
  for (const [task, x] of a) {
    const y = b.get(task);
    if (y) ds.push(y.mean - x.mean);
  }
  return stat(ds, ds.length);
}

/** Whether a difference is better (1), worse (-1) or not distinguishable from zero (0) at 95%. */
export function verdict(d: MetricStat | null, m: MetricDef): -1 | 0 | 1 {
  if (!d?.ci || (d.ci[0] <= 0 && d.ci[1] >= 0)) return 0;
  return d.mean > 0 === m.higherIsBetter ? 1 : -1;
}

/** Position of a value in the metric's range, 0 (worst) … 1 (best); null without a range. */
export function goodness(v: number | null, m: MetricDef): number | null {
  if (v === null || !m.range) return null;
  const [lo, hi] = m.range;
  if (hi <= lo) return null;
  const f = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  return m.higherIsBetter ? f : 1 - f;
}

/** A number with about three significant digits (never exponent notation for usual magnitudes). */
export function fmtNumber(v: number): string {
  const a = Math.abs(v);
  const d = a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : 3;
  return Number(v.toFixed(d)).toString();
}

/** `72.5%`, `48.3 pts`, `$1.24`; signed `%` values are points (`+3.2 pt`); `—` for no value. */
export function fmtMetric(v: number | null | undefined, m: MetricDef, signed = false): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = signed && v > 0 ? "+" : "";
  const n = m.unit === "%" ? v.toFixed(1) : fmtNumber(v);
  if (!m.unit) return `${sign}${n}`;
  // A difference of two percentages is in percentage points.
  if (m.unit === "%") return signed ? `${sign}${n} pt` : `${n}%`;
  if (m.unit === "$") return `${sign}$${n}`;
  return `${sign}${n} ${m.unit}`;
}

/** Half width of the 95% CI, e.g. `±3.2`; empty without one. */
export function fmtCi(s: MetricStat | null | undefined, m: MetricDef): string {
  if (!s?.ci) return "";
  const h = (s.ci[1] - s.ci[0]) / 2;
  return `±${m.unit === "%" ? h.toFixed(1) : fmtNumber(h)}`;
}
