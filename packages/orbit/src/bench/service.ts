// Benchmark jobs: each Trial (task × method × seed) is a solve Run and a separate verify Run on the
// same lease model as every other run. BenchService advances trials when their runs change, and
// recovers open trials from the store after a daemon restart.
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import type { AuthStore } from "../auth/index.ts";
import type { OrbitPaths } from "../config/paths.ts";
import {
  type BenchCompare,
  type BenchJob,
  type BenchJobDetail,
  type BenchJobList,
  BenchJobSpec,
  type BenchJobSpecInput,
  type Benchmark,
  type BenchTask,
  isTerminal,
  type Method,
  type MethodSummary,
  type Outcome,
  type Run,
  type RunSpecInput,
  type Trial,
} from "../contracts/index.ts";
import { newId, nowIso } from "../lib/ids.ts";
import { NotFoundError, type RunService, UserError } from "../runs/service.ts";
import type { Store } from "../store/index.ts";
import type { Adapter, TrialContext } from "./adapter.ts";
import { asiAdapter } from "./asi.ts";
import { classify, solveVerdict } from "./classify.ts";
import { harborAdapter } from "./harbor.ts";
import type { BenchmarkRegistry } from "./registry.ts";

export interface BenchServiceDeps {
  store: Store;
  runs: RunService;
  registry: BenchmarkRegistry;
  paths: OrbitPaths;
  auth?: AuthStore;
  log?: (msg: string) => void;
}

/** Group of a job's runs, so the run list and notifications see a job as one group. */
export const benchGroup = (jobId: string) => `bench-${jobId}`;

const pct = (o: Outcome) =>
  o.score === null || o.maxScore <= 0 ? null : (100 * o.score) / o.maxScore;
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

export function summarize(methods: string[], trials: Trial[]): MethodSummary[] {
  return methods.map((method) => {
    const ts = trials.filter((t) => t.method === method);
    const done = ts.filter((t) => t.outcome);
    const count = (e: Outcome["evaluation"]) =>
      done.filter((t) => t.outcome?.evaluation === e).length;
    const scores = done
      .filter((t) => t.outcome?.evaluation === "valid")
      .map((t) => pct(t.outcome as Outcome))
      .filter((x): x is number => x !== null);
    return {
      method,
      trials: ts.length,
      valid: count("valid"),
      invalid: count("invalid"),
      unknown: count("unknown"),
      pending: ts.length - done.length,
      meanPct: mean(scores),
    };
  });
}

/**
 * Columns `<job>/<method>`, one row per task; a cell is the mean percent over the valid trials.
 * `paired` means use only tasks valid in every column, so methods are compared on the same tasks.
 */
export function compareJobs(jobs: { job: BenchJob; trials: Trial[] }[]): BenchCompare {
  // Jobs may share a name: fall back to the job id so every column key is unique.
  const keys = new Set<string>();
  const columns = jobs.flatMap(({ job }) =>
    job.spec.methods.map((m) => {
      let key = jobs.length > 1 ? `${job.spec.name ?? job.id}/${m.name}` : m.name;
      if (keys.has(key)) key = `${job.id}/${m.name}`;
      keys.add(key);
      return { key, jobId: job.id, method: m.name };
    }),
  );
  const tasks = [...new Set(jobs.flatMap(({ trials }) => trials.map((t) => t.task)))].sort();
  const rows = tasks.map((task) => {
    const cells: Record<string, number | null> = {};
    const counts: Record<string, string> = {};
    for (const c of columns) {
      const ts = (jobs.find((j) => j.job.id === c.jobId)?.trials ?? []).filter(
        (t) => t.task === task && t.method === c.method,
      );
      const valid = ts
        .filter((t) => t.outcome?.evaluation === "valid")
        .map((t) => pct(t.outcome as Outcome))
        .filter((x): x is number => x !== null);
      cells[c.key] = mean(valid);
      counts[c.key] = ts.length ? `${valid.length}/${ts.length}` : "";
    }
    return { task, cells, counts };
  });
  const paired = rows.filter((r) => columns.every((c) => r.cells[c.key] != null));
  const means: BenchCompare["means"] = {};
  for (const c of columns) {
    const col = (rs: typeof rows) =>
      mean(rs.map((r) => r.cells[c.key]).filter((x): x is number => x != null));
    means[c.key] = { all: col(rows), paired: col(paired) };
  }
  return { columns, rows, means, pairedTasks: paired.length };
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

  /** Pick up trials left open by a previous daemon (after RunService has recovered its runs). */
  async start(): Promise<void> {
    for (const t of this.deps.store.openTrials()) await this.advance(t.id);
  }

  // ---- benchmarks ----

  benchmark(name: string): Benchmark {
    const b = this.deps.registry.get(name);
    if (!b) throw new NotFoundError(`benchmark not found: ${name}`);
    return b;
  }

  private adapter(b: Benchmark): Adapter {
    if (b.adapter === "harbor") return harborAdapter;
    return asiAdapter((m) =>
      m.auth ? Boolean(this.deps.auth?.get(m.auth)?.profile.hostNetwork) : false,
    );
  }

  tasks(name: string): BenchTask[] {
    const b = this.benchmark(name);
    if (!existsSync(b.path)) throw new UserError(`benchmark path not found: ${b.path}`);
    return this.adapter(b).tasks(b);
  }

  // ---- jobs ----

  async submit(input: BenchJobSpecInput): Promise<BenchJob> {
    const parsed = BenchJobSpec.safeParse(input);
    if (!parsed.success) throw new UserError(parsed.error.issues.map((i) => i.message).join("; "));
    const spec = parsed.data;
    const b = this.benchmark(spec.benchmark);
    const all = this.tasks(b.name);
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
    const job: BenchJob = {
      id: newId(),
      spec,
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
    for (const id of ids) await this.advance(id);
    return this.deps.store.getJob(job.id) ?? job;
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
        ),
      })),
    };
  }

  compare(ids: string[]): BenchCompare {
    if (ids.length === 0) throw new UserError("no jobs to compare");
    if (new Set(ids).size !== ids.length) throw new UserError("a job is listed more than once");
    return compareJobs(ids.map((id) => this.job(id)));
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

  private context(job: BenchJob, t: Trial): TrialContext {
    const method = job.spec.methods.find((m) => m.name === t.method);
    if (!method) throw new Error(`method ${t.method} not in job ${job.id}`);
    return {
      benchmark: this.benchmark(job.spec.benchmark),
      task: t.task,
      method,
      seed: t.seed,
      options: job.spec.options,
      timeoutMin: job.spec.timeoutMin,
      staging: join(this.deps.paths.bench, job.id, t.id),
    };
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
      let ctx: TrialContext;
      let spec: RunSpecInput;
      try {
        ctx = this.context(job, t);
        spec = this.adapter(ctx.benchmark).solveSpec(ctx);
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
      let plan: ReturnType<Adapter["verifySpec"]>;
      try {
        const ctx = this.context(job, t);
        plan = this.adapter(ctx.benchmark).verifySpec(ctx, solve, runs.dirs(solve.id).output);
      } catch (e) {
        return this.finish(t, failed(solve, t.issues, `verify spec: ${(e as Error).message}`));
      }
      t.issues = [...t.issues, ...plan.issues];
      try {
        const run = await this.submitRun(job, t, "verify", plan.spec);
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
    let score = null;
    if (verify.startedAt && verify.state !== "cancelled" && verify.state !== "lost") {
      try {
        const ctx = this.context(job, t);
        score = this.adapter(ctx.benchmark).score(
          ctx,
          solve,
          runs.dirs(solve.id).output,
          runs.dirs(verify.id).output,
        );
      } catch (e) {
        score = {
          score: null,
          maxScore: 1,
          issues: [`score: ${(e as Error).message}`],
          invalid: true,
        };
      }
    }
    this.finish(t, classify(solve, verify, score, t.issues));
  }
}
