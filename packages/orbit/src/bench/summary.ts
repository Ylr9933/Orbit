import type {
  BenchCompare,
  BenchJob,
  MethodSummary,
  MetricSpec,
  Outcome,
  Trial,
} from "../contracts/index.ts";
import { aggregate, pairedDiff, resolveMetrics, taskMeans } from "../contracts/metrics.ts";

export const isValid = (t: Trial) => t.outcome?.evaluation === "valid";

/** Per method: trial counts and every metric over its valid trials (per task first, then tasks). */
export function summarize(
  methods: string[],
  trials: Trial[],
  metrics: MetricSpec[] = [],
): MethodSummary[] {
  const specs = resolveMetrics(metrics);
  return methods.map((method) => {
    const ts = trials.filter((t) => t.method === method);
    const done = ts.filter((t) => t.outcome);
    const count = (e: Outcome["evaluation"]) =>
      done.filter((t) => t.outcome?.evaluation === e).length;
    const valid = done.filter(isValid);
    return {
      method,
      trials: ts.length,
      valid: valid.length,
      invalid: count("invalid"),
      unknown: count("unknown"),
      pending: ts.length - done.length,
      metrics: Object.fromEntries(specs.map((m) => [m.name, aggregate(taskMeans(valid, m.name))])),
    };
  });
}

/** Metrics shared by all jobs, as the first job declares them; its primary stays primary. */
function sharedMetrics(jobs: BenchJob[]): MetricSpec[] {
  const [first, ...rest] = jobs.map((j) => resolveMetrics(j.metrics));
  const shared = (first ?? []).filter((m) => rest.every((ms) => ms.some((x) => x.name === m.name)));
  return resolveMetrics(shared);
}

/**
 * Columns `<job>/<method>`, one row per task. Per metric, a cell is the mean over the task's valid
 * trials; column means are over all its tasks and over the tasks every column has (`paired`), and
 * `diff` is the paired difference to the first column, so methods are compared on the same tasks.
 */
export function compareJobs(jobs: { job: BenchJob; trials: Trial[] }[]): BenchCompare {
  // Jobs may share a name: fall back to the job id so every column key is unique.
  const keys = new Set<string>();
  const columns = jobs.flatMap(({ job, trials }) =>
    job.spec.methods.map((m) => {
      let key = jobs.length > 1 ? `${job.spec.name ?? job.id}/${m.name}` : m.name;
      if (keys.has(key)) key = `${job.id}/${m.name}`;
      keys.add(key);
      const own = trials.filter((t) => t.method === m.name);
      return { key, jobId: job.id, method: m.name, trials: own, valid: own.filter(isValid) };
    }),
  );
  const metrics = sharedMetrics(jobs.map((j) => j.job));
  const tasks = [...new Set(jobs.flatMap(({ trials }) => trials.map((t) => t.task)))].sort();
  const means = Object.fromEntries(
    metrics.map((m) => [m.name, columns.map((c) => taskMeans(c.valid, m.name))]),
  );
  const rows = tasks.map((task) => ({
    task,
    counts: Object.fromEntries(
      columns.map((c) => {
        const ts = c.trials.filter((t) => t.task === task);
        return [c.key, ts.length ? `${ts.filter(isValid).length}/${ts.length}` : ""];
      }),
    ),
    values: Object.fromEntries(
      metrics.map((m) => [
        m.name,
        Object.fromEntries(
          columns.map((c, i) => [c.key, means[m.name]?.[i]?.get(task)?.mean ?? null]),
        ),
      ]),
    ),
  }));
  const stats: BenchCompare["stats"] = {};
  for (const m of metrics) {
    const ms = means[m.name] ?? [];
    const paired = new Set(tasks.filter((task) => ms.every((x) => x.has(task))));
    const base = ms[0];
    stats[m.name] = {
      pairedTasks: paired.size,
      columns: Object.fromEntries(
        columns.map((c, i) => {
          const x = ms[i] ?? new Map();
          return [
            c.key,
            {
              all: aggregate(x),
              paired: aggregate(x, paired),
              diff: i > 0 && base ? pairedDiff(base, x) : null,
            },
          ];
        }),
      ),
    };
  }
  return {
    columns: columns.map(({ key, jobId, method }) => ({ key, jobId, method })),
    metrics,
    rows,
    stats,
  };
}
