// Benchmark jobs: each Trial (task × method × seed) is a solve Run and a separate verify Run on the
// same lease model as every other run. BenchService advances trials when their runs change, and
// recovers open trials from the store after a daemon restart.
import { appendFileSync, existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import type { AuthStore } from "../auth/index.ts";
import type { OrbitPaths } from "../config/paths.ts";
import {
  type AdapterTasksResponse,
  type BenchCompare,
  type BenchJob,
  type BenchJobDetail,
  type BenchJobList,
  BenchJobSpec,
  type BenchJobSpecInput,
  type Benchmark,
  type BenchTask,
  type BenchUsage,
  isTerminal,
  type Method,
  type MethodSummary,
  type MetricSpec,
  type Outcome,
  type Run,
  type RunDeletion,
  type RunSpecInput,
  type ScoreResult,
  type Trial,
} from "../contracts/index.ts";
import {
  aggregate,
  metricValue,
  pairedDiff,
  resolveMetrics,
  taskMeans,
} from "../contracts/metrics.ts";
import { newId, nowIso } from "../lib/ids.ts";
import { NotFoundError, type RunService, UserError } from "../runs/service.ts";
import { runAgentFailure } from "../sessions/index.ts";
import type { Store } from "../store/index.ts";
import { classify, solveVerdict } from "./classify.ts";
import { AdapterClient, type TrialInput, toRunSpec } from "./protocol.ts";
import type { BenchmarkRegistry } from "./registry.ts";
import { applyOverride, loadResources, resolveResources, usageRow } from "./resources.ts";

export interface BenchServiceDeps {
  store: Store;
  runs: RunService;
  registry: BenchmarkRegistry;
  paths: OrbitPaths;
  auth?: AuthStore;
  /** Command running this orbit binary; built-in adapters run as `<self> __adapter <name>`. */
  self?: string[];
  log?: (msg: string) => void;
}

/** Group of a job's runs, so the run list and notifications see a job as one group. */
export const benchGroup = (jobId: string) => `bench-${jobId}`;

const isValid = (t: Trial) => t.outcome?.evaluation === "valid";

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

/** Verification could not be set up: keep the solve's issues and add why. */
function failed(solve: Run, issues: string[], issue: string): Outcome {
  const c = classify(solve, null, null, issues);
  return {
    ...c,
    evaluation: "invalid",
    issues: [...c.issues.filter((i) => i !== "verify not run"), issue],
  };
}

export class BenchService {
  private readonly deps: BenchServiceDeps;
  /** Trials being advanced, and those changed meanwhile (advanced once more afterwards). */
  private readonly busy = new Set<string>();
  private readonly again = new Set<string>();

  constructor(deps: BenchServiceDeps) {
    this.deps = deps;
    deps.runs.on("change", ({ run }) => this.onRun(run));
  }

  /**
   * Pick up trials left open by a previous daemon (after RunService has recovered its runs), in the
   * background: advancing them may call adapters, which must not hold up the daemon's start.
   */
  start(): void {
    this.advanceAll(this.deps.store.openTrials().map((t) => t.id));
  }

  /** Advance trials one after another in the background (each may run adapter processes). */
  private advanceAll(ids: string[]): void {
    void (async () => {
      for (const id of ids) await this.advance(id);
    })();
  }

  // ---- benchmarks ----

  benchmark(name: string): Benchmark {
    const b = this.deps.registry.get(name);
    if (!b) throw new NotFoundError(`benchmark not found: ${name}`);
    return b;
  }

  private adapter(b: Benchmark): AdapterClient {
    return new AdapterClient(b, this.deps.self);
  }

  /** Tasks and metrics as the adapter lists them; adapter failures are the user's to fix. */
  async infoOf(b: Benchmark): Promise<AdapterTasksResponse> {
    if (!existsSync(b.path)) throw new UserError(`benchmark path not found: ${b.path}`);
    try {
      return await this.adapter(b).tasks();
    } catch (e) {
      throw new UserError((e as Error).message);
    }
  }

  async tasks(name: string): Promise<BenchTask[]> {
    return (await this.infoOf(this.benchmark(name))).tasks;
  }

  // ---- jobs ----

  async submit(input: BenchJobSpecInput): Promise<BenchJob> {
    const parsed = BenchJobSpec.safeParse(input);
    if (!parsed.success) throw new UserError(parsed.error.issues.map((i) => i.message).join("; "));
    const spec = parsed.data;
    const b = this.benchmark(spec.benchmark);
    const info = await this.infoOf(b);
    const all = info.tasks;
    const names = new Set<string>();
    for (const m of spec.methods) {
      if (names.has(m.name)) throw new UserError(`duplicate method name: ${m.name}`);
      names.add(m.name);
      this.checkMethod(m);
    }
    if (spec.tasks.length === 0) spec.tasks = all.filter((t) => t.supported).map((t) => t.id);
    for (const id of spec.tasks) {
      const t = all.find((x) => x.id === id);
      if (!t) throw new UserError(`task not found in ${b.name}: ${id}`);
      if (!t.supported) throw new UserError(`task ${id} is not supported: ${t.reason}`);
    }
    if (spec.tasks.length === 0) throw new UserError(`${b.name} has no supported tasks`);
    let resources: BenchJob["resources"] = null;
    if (b.resources) {
      try {
        resources = resolveResources(
          loadResources(b.resources),
          spec.tasks,
          all.map((t) => t.id),
        );
      } catch (e) {
        throw new UserError((e as Error).message);
      }
    }
    const job: BenchJob = {
      id: newId(),
      spec,
      resources,
      metrics: resolveMetrics(info.metrics),
      state: "running",
      createdAt: nowIso(),
      endedAt: null,
    };
    this.deps.store.putJob(job);
    let n = 0;
    const ids: string[] = [];
    for (const task of spec.tasks)
      for (const m of spec.methods)
        for (let seed = 1; seed <= spec.seeds; seed++) {
          const t: Trial = {
            id: `${job.id}.${String(++n).padStart(5, "0")}`,
            jobId: job.id,
            task,
            method: m.name,
            seed,
            state: "pending",
            solveRunId: null,
            verifyRunId: null,
            issues: [],
            outcome: null,
            createdAt: job.createdAt,
            endedAt: null,
          };
          this.deps.store.putTrial(t);
          ids.push(t.id);
        }
    this.advanceAll(ids);
    return job;
  }

  private checkMethod(m: Method): void {
    if (m.agent === "oracle" || m.agent === "empty") {
      if (m.auth || m.bundle || m.model)
        throw new UserError(`${m.name}: ${m.agent} takes no auth, model or bundle`);
      return;
    }
    const entry = m.auth ? this.deps.auth?.get(m.auth) : null;
    if (!entry) throw new UserError(`${m.name}: auth profile not found: ${m.auth}`);
    if (entry.profile.harness !== m.agent)
      throw new UserError(
        `${m.name}: auth profile ${m.auth} is for ${entry.profile.harness}, not ${m.agent}`,
      );
  }

  job(id: string): BenchJobDetail {
    const job = this.deps.store.getJob(id);
    if (!job) throw new NotFoundError(`bench job not found: ${id}`);
    const trials = this.deps.store.trials(id);
    return {
      job,
      trials,
      summary: summarize(
        job.spec.methods.map((m) => m.name),
        trials,
        job.metrics,
      ),
    };
  }

  jobs(limit = 200): BenchJobList {
    return {
      jobs: this.deps.store.listJobs(limit).map((job) => ({
        ...job,
        summary: summarize(
          job.spec.methods.map((m) => m.name),
          this.deps.store.trials(job.id),
          job.metrics,
        ),
      })),
    };
  }

  compare(ids: string[]): BenchCompare {
    if (ids.length === 0) throw new UserError("no jobs to compare");
    if (new Set(ids).size !== ids.length) throw new UserError("a job is listed more than once");
    return compareJobs(ids.map((id) => this.job(id)));
  }

  /** Measured solve use per task over the given jobs, with suggested resources (never applied). */
  usage(ids: string[]): BenchUsage {
    if (ids.length === 0) throw new UserError("no jobs given");
    const runs = new Map<string, Run[]>();
    const requested = new Map<string, Run["spec"]>();
    for (const id of ids) {
      const d = this.job(id);
      // Only Agent methods show what a task needs; oracle and empty runs say nothing about it.
      const agents = new Set(
        d.job.spec.methods
          .filter((m) => m.agent === "codex" || m.agent === "claude-code")
          .map((m) => m.name),
      );
      for (const t of d.trials) {
        if (!agents.has(t.method)) continue;
        const r = t.solveRunId ? this.deps.runs.get(t.solveRunId) : null;
        if (!r || !isTerminal(r.state)) continue;
        runs.set(t.task, [...(runs.get(t.task) ?? []), r]);
        // The latest job's request is what a suggestion is compared against.
        requested.set(t.task, r.spec);
      }
    }
    const rows = [...runs.keys()].sort().map((task) => {
      const s = requested.get(task) as Run["spec"];
      const { cpus, memGB, gpus, gpuMemGB } = s.resources;
      return usageRow(
        task,
        { cpus, memGB, gpus, ...(gpuMemGB ? { gpuMemGB } : {}), timeoutMin: s.timeoutMin },
        runs.get(task) ?? [],
      );
    });
    return { jobs: ids, rows };
  }

  /**
   * Delete a finished or cancelled job: its trials, all their solve and verify runs (with their
   * directories) and its staging files. Irreversible; refused while any of its runs is not done.
   */
  async deleteJob(id: string): Promise<RunDeletion> {
    const job = this.deps.store.getJob(id);
    if (!job) throw new NotFoundError(`bench job not found: ${id}`);
    if (job.state === "running") throw new UserError(`bench job ${id} is running; cancel it first`);
    const trials = this.deps.store.trials(id);
    if (trials.some((t) => this.busy.has(t.id)))
      throw new UserError(`bench job ${id} is still being updated; try again shortly`);
    const ids = trials
      .flatMap((t) => [t.solveRunId, t.verifyRunId])
      .filter((r): r is string => Boolean(r && this.deps.runs.get(r)));
    const out = await this.deps.runs.delete(ids, { forJob: true });
    this.deps.store.deleteJob(id);
    rmSync(join(this.deps.paths.bench, id), { recursive: true, force: true });
    return out;
  }

  async cancel(id: string): Promise<BenchJob> {
    const job = this.deps.store.getJob(id);
    if (!job) throw new NotFoundError(`bench job not found: ${id}`);
    if (job.state !== "running") return job;
    job.state = "cancelled";
    job.endedAt = nowIso();
    this.deps.store.putJob(job);
    for (const t of this.deps.store.trials(id)) {
      if (t.state === "done") continue;
      const runId =
        t.state === "solving" ? t.solveRunId : t.state === "verifying" ? t.verifyRunId : null;
      if (runId) await this.deps.runs.cancel(runId).catch(() => undefined);
      await this.advance(t.id);
    }
    return job;
  }

  // ---- trial state machine ----

  private onRun(run: Run): void {
    const t = this.deps.store.trialByRun(run.id);
    if (t) void this.advance(t.id);
  }

  private async advance(id: string): Promise<void> {
    if (this.busy.has(id)) {
      this.again.add(id);
      return;
    }
    this.busy.add(id);
    try {
      do {
        this.again.delete(id);
        await this.step(id);
      } while (this.again.has(id));
    } catch (e) {
      this.deps.log?.(`bench trial ${id}: ${(e as Error).message}`);
    } finally {
      this.busy.delete(id);
    }
  }

  private context(job: BenchJob, t: Trial): { b: Benchmark; trial: TrialInput } {
    const method = job.spec.methods.find((m) => m.name === t.method);
    if (!method) throw new Error(`method ${t.method} not in job ${job.id}`);
    return {
      b: this.benchmark(job.spec.benchmark),
      trial: {
        id: t.id,
        task: t.task,
        method,
        seed: t.seed,
        options: job.spec.options,
        timeoutMin: job.spec.timeoutMin,
        staging: join(this.deps.paths.bench, job.id, t.id),
        hostNetwork: method.auth
          ? Boolean(this.deps.auth?.get(method.auth)?.profile.hostNetwork)
          : false,
      },
    };
  }

  private ref(run: Run) {
    return { run, output: this.deps.runs.dirs(run.id).output };
  }

  private async submitRun(job: BenchJob, t: Trial, phase: "solve" | "verify", spec: RunSpecInput) {
    return this.deps.runs.submit({
      ...spec,
      // Scoring reads run outputs from this node's disk, so benchmark runs stay here.
      resources: { ...spec.resources, node: this.deps.runs.nodeName },
      name: `${t.task} · ${t.method}${job.spec.seeds > 1 ? ` #${t.seed}` : ""} · ${phase}`,
      group: benchGroup(job.id),
      tags: {
        ...spec.tags,
        bench: job.spec.benchmark,
        job: job.id,
        trial: t.id,
        phase,
      },
      params: { task: t.task, method: t.method, seed: String(t.seed), phase },
    });
  }

  private finish(t: Trial, outcome: Outcome): void {
    t.state = "done";
    t.outcome = outcome;
    t.endedAt = nowIso();
    this.deps.store.putTrial(t);
    const job = this.deps.store.getJob(t.jobId);
    if (job) {
      rmSync(join(this.deps.paths.bench, job.id, t.id), { recursive: true, force: true });
      if (
        job.state === "running" &&
        this.deps.store.trials(job.id).every((x) => x.state === "done")
      ) {
        job.state = "done";
        job.endedAt = nowIso();
        this.deps.store.putJob(job);
      }
    }
  }

  /** A job cancelled while a run was being submitted: cancel that run too. */
  private async cancelIfJobCancelled(jobId: string, runId: string): Promise<void> {
    if (this.deps.store.getJob(jobId)?.state === "cancelled")
      await this.deps.runs.cancel(runId).catch(() => undefined);
  }

  private skipped(t: Trial, evaluation: Outcome["evaluation"], issue: string): void {
    this.finish(t, {
      execution: "skipped",
      evaluation,
      score: null,
      maxScore: 1,
      issues: [...t.issues, issue],
      cleanup: "done",
      review: null,
    });
  }

  private async step(id: string): Promise<void> {
    const t = this.deps.store.getTrial(id);
    const job = t ? this.deps.store.getJob(t.jobId) : null;
    if (!t || !job) return;
    const runs = this.deps.runs;

    if (t.state === "done") {
      // Only the cleanup status can still change (runs are cleaned up after they end).
      if (t.outcome?.cleanup !== "pending") return;
      const rs = [t.solveRunId, t.verifyRunId].map((r) => (r ? runs.get(r) : null));
      const cleanup = rs.some((r) => r?.cleanup === "failed")
        ? "failed"
        : rs.some((r) => r?.cleanup === "pending")
          ? "pending"
          : "done";
      if (cleanup !== "pending") {
        t.outcome.cleanup = cleanup;
        this.deps.store.putTrial(t);
      }
      return;
    }

    if (t.state === "pending") {
      if (job.state === "cancelled") return this.skipped(t, "unknown", "job cancelled");
      let spec: RunSpecInput;
      try {
        const { b, trial } = this.context(job, t);
        const reply = await this.adapter(b).solve(trial);
        spec = applyOverride(
          toRunSpec(reply.spec, trial.method, b, "solve"),
          job.resources?.[t.task],
          job.spec.timeoutMin !== undefined,
        );
        t.issues = [...t.issues, ...reply.issues];
      } catch (e) {
        return this.skipped(t, "invalid", `solve spec: ${(e as Error).message}`);
      }
      try {
        const run = await this.submitRun(job, t, "solve", spec);
        t.solveRunId = run.id;
        t.state = "solving";
        this.deps.store.putTrial(t);
        await this.cancelIfJobCancelled(job.id, run.id);
      } catch (e) {
        return this.skipped(t, "invalid", `solve rejected: ${(e as Error).message}`);
      }
      return;
    }

    const solve = t.solveRunId ? runs.get(t.solveRunId) : null;
    if (!solve) return this.skipped(t, "unknown", "solve run missing");

    if (t.state === "solving") {
      if (!isTerminal(solve.state)) return this.cancelIfJobCancelled(job.id, solve.id);
      const sv = solveVerdict(solve);
      if (!sv.verify || job.state === "cancelled") {
        const outcome = classify(solve, null, null, t.issues);
        if (sv.verify) {
          outcome.evaluation = "unknown";
          outcome.issues.push("job cancelled before verification");
        }
        return this.finish(t, outcome);
      }
      let spec: RunSpecInput;
      try {
        const { b, trial } = this.context(job, t);
        const reply = await this.adapter(b).verify(trial, this.ref(solve));
        spec = toRunSpec(reply.spec, trial.method, b, "verify");
        t.issues = [...t.issues, ...reply.issues];
      } catch (e) {
        return this.finish(t, failed(solve, t.issues, `verify spec: ${(e as Error).message}`));
      }
      try {
        const run = await this.submitRun(job, t, "verify", spec);
        t.verifyRunId = run.id;
        t.state = "verifying";
        this.deps.store.putTrial(t);
        await this.cancelIfJobCancelled(job.id, run.id);
      } catch (e) {
        return this.finish(t, failed(solve, t.issues, `verify rejected: ${(e as Error).message}`));
      }
      return;
    }

    // verifying
    const verify = t.verifyRunId ? runs.get(t.verifyRunId) : null;
    if (!verify)
      return this.finish(t, classify(solve, null, null, [...t.issues, "verify run missing"]));
    if (!isTerminal(verify.state)) return this.cancelIfJobCancelled(job.id, verify.id);
    let score: ScoreResult | null = null;
    if (verify.startedAt && verify.state !== "cancelled" && verify.state !== "lost") {
      try {
        const { b, trial } = this.context(job, t);
        score = await this.adapter(b).score(trial, this.ref(solve), this.ref(verify));
      } catch (e) {
        score = {
          score: null,
          maxScore: 1,
          issues: [`score: ${(e as Error).message}`],
          invalid: true,
        };
      }
    }
    const agent = await runAgentFailure(runs.dirs(solve.id).agent).catch(() => null);
    const outcome = classify(solve, verify, score, t.issues, agent);
    this.recordMetrics(job, verify, outcome);
    this.finish(t, outcome);
  }

  /**
   * The trial's metric values as one line of the verify run's metrics (`bench/<name>`), so the run
   * page and run comparison show them like any other run's metrics.
   */
  private recordMetrics(job: BenchJob, verify: Run, o: Outcome): void {
    const line: Record<string, number> = {};
    for (const m of resolveMetrics(job.metrics)) {
      const v = metricValue(o, m.name);
      if (v !== null) line[`bench/${m.name}`] = v;
    }
    if (Object.keys(line).length === 0) return;
    try {
      appendFileSync(this.deps.runs.dirs(verify.id).metrics, `${JSON.stringify(line)}\n`);
    } catch (e) {
      this.deps.log?.(`bench trial metrics of ${verify.id}: ${(e as Error).message}`);
    }
  }
}
