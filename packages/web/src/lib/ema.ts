/**
 * Debiased exponential moving average (TensorBoard/W&B style) over a series that may be
 * irregularly spaced. `weight` in [0, 1); 0 disables smoothing.
 */
export function ema(values: readonly number[], weight: number): number[] {
  if (weight <= 0) return [...values];
  const out: number[] = [];
  let last = 0;
  let n = 0;
  for (const v of values) {
    if (!Number.isFinite(v)) {
      out.push(v);
      continue;
    }
    last = last * weight + (1 - weight) * v;
    n++;
    out.push(last / (1 - weight ** n));
  }
  return out;
}

export function stats(values: readonly number[]): {
  min: number;
  max: number;
  mean: number;
  std: number;
} {
  const v = values.filter(Number.isFinite);
  if (!v.length) return { min: Number.NaN, max: Number.NaN, mean: Number.NaN, std: Number.NaN };
  const mean = v.reduce((a, b) => a + b, 0) / v.length;
  const std =
    v.length > 1 ? Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / (v.length - 1)) : 0;
  return { min: Math.min(...v), max: Math.max(...v), mean, std };
}
