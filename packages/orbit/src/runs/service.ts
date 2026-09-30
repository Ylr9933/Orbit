import type { ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import { appendFileSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { hostname, userInfo } from "node:os";
import { basename, dirname, isAbsolute, join, resolve } from "node:path";
import { type OrbitPaths, type RunDirs, runDirs } from "../config/paths.ts";
import {
  isTerminal,
  type Lease,
  type NodeResources,
  type Run,
  type RunEvent,
  RunSpec,
  type RunSpecInput,
  type RunState,
} from "../contracts/index.ts";
import * as docker from "../executor/docker.ts";
import { newId, nowIso } from "../lib/ids.ts";
import { allocate, infeasible } from "../resources/allocate.ts";
import { resolveAgentRef } from "../sessions/index.ts";
import type { RunFilter, Store } from "../store/index.ts";
import { snapshotProject } from "../workspace/snapshot.ts";

export interface RunServiceDeps {
  store: Store;
  paths: OrbitPaths;
  probe: () => Promise<NodeResources>;
  /** Scheduler period; the loop also runs after every submit/finish. */
  tickMs?: number;
}

export interface RunChange {
  run: Run;
  event?: RunEvent;
}

const PROBE_TTL_MS = 2000;
const LOG_DRAIN_TIMEOUT_MS = 15_000;

/**
 * The single owner of Run state on this node: submission, queueing, leases, container lifecycle,
 * evidence collection and cleanup. Emits "change" for every persisted update.
 */
export class RunService extends EventEmitter<{ change: [RunChange] }> {
  private readonly store: Store;
  private readonly paths: OrbitPaths;
  private readonly probeFn: () => Promise<NodeResources>;
  private readonly homeLabel: string;
  private readonly node = hostname();
  private readonly gpuMode = docker.detectGpuMode();
  private cached: { at: number; value: NodeResources } | null = null;
  private timer: NodeJS.Timeout | null = null;
  private ticking: Promise<void> | null = null;
  private tickAgain = false;
  /** Runs with an active launch/watch task in this process. */
  private readonly active = new Map<
    string,
    { cancel?: "cancel" | "timeout"; logs?: ChildProcess }
  >();

  private readonly deps: RunServiceDeps;

  constructor(deps: RunServiceDeps) {
    super();
    this.deps = deps;
    this.store = deps.store;
    this.paths = deps.paths;
    this.probeFn = deps.probe;
    this.homeLabel = createHash("sha256")
      .update(resolve(deps.paths.home))
      .digest("hex")
      .slice(0, 12);
  }

  // ---- public API ----

  async start(): Promise<void> {
    await this.recover();
    this.timer = setInterval(() => void this.tick(), this.deps.tickMs ?? 3000);
    void this.tick();
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    await this.ticking;
    for (const a of this.active.values()) a.logs?.kill();
  }

  async resources(force = false): Promise<NodeResources> {
    if (!force && this.cached && Date.now() - this.cached.at < PROBE_TTL_MS)
      return this.cached.value;
    const value = await this.probeFn();
    this.cached = { at: Date.now(), value };
    return value;
  }

  get(id: string): Run | null {
    return this.store.getRun(id);
  }

  storeList(filter: RunFilter): Run[] {
    return this.store.listRuns(filter);
  }

  events(id: string, afterSeq = 0): RunEvent[] {
    return this.store.events(id, afterSeq);
  }

  async submit(input: RunSpecInput): Promise<Run> {
    const spec = RunSpec.parse(input);
    const why = infeasible(spec.resources, await this.resources());
    if (why) throw new UserError(why);
    if (spec.project && !isAbsolute(spec.project))
      throw new UserError("project must be an absolute path");
    for (const m of spec.mounts) {
      if (!isAbsolute(m.source) || !existsSync(m.source))
        throw new UserError(`mount source not found: ${m.source}`);
    }
    if (spec.dockerfile) {
      const df = isAbsolute(spec.dockerfile)
        ? spec.dockerfile
        : resolve(spec.project ?? "/", spec.dockerfile);
      if (!existsSync(df)) throw new UserError(`dockerfile not found: ${df}`);
      spec.dockerfile = df;
    }
    if (spec.agent) spec.agent = await resolveAgentRef(spec.agent);

    const id = newId();
    const dirs = runDirs(this.paths, id);
    mkdirSync(dirs.output, { recursive: true });
    writeFileSync(dirs.metrics, "");
    writeFileSync(dirs.log, "");
    let code: Run["code"] = null;
    if (spec.project && spec.snapshot) {
      try {
        code = await snapshotProject(spec.project, dirs.workspace, dirs.diff);
      } catch (e) {
        rmSync(dirs.root, { recursive: true, force: true });
        throw new UserError(`snapshot failed: ${(e as Error).message}`);
      }
    }
    const run: Run = {
      id,
      spec,
      state: "queued",
      reason: null,
      exitCode: null,
      node: this.node,
      image: spec.image ?? null,
      containerId: null,
      lease: null,
      code,
      cleanup: "pending",
      note: "",
      createdAt: nowIso(),
      startedAt: null,
      endedAt: null,
    };
    this.save(
      run,
      "submitted",
      code
        ? `snapshot ${code.commit?.slice(0, 8) ?? "(no commit)"}${code.dirty ? " +dirty" : ""}, ${code.fileCount} files`
        : "no snapshot",
    );
    void this.tick();
    return run;
  }

  async cancel(id: string): Promise<Run> {
    const run = this.mustGet(id);
    if (isTerminal(run.state)) return run;
    if (run.state === "queued") {
      return this.finalize(run, "cancelled", null, "cancelled while queued");
    }
    this.requestStop(run, "cancel");
    return this.mustGet(id);
  }

  setNote(id: string, note: string): Run {
    const run = this.mustGet(id);
    run.note = note;
    this.save(run, "note", note.length > 200 ? `${note.slice(0, 200)}…` : note);
    return run;
  }

  ledger(): { leases: Lease[]; queued: { runId: string; reason: string | null }[] } {
    return {
      leases: this.store.activeLeases(),
      queued: this.store.queuedRuns().map((r) => ({ runId: r.id, reason: r.reason })),
    };
  }

  dirs(id: string): RunDirs {
    return runDirs(this.paths, id);
  }

  // ---- scheduling ----

  /** Run one scheduling pass; concurrent calls coalesce into at most one extra pass. */
  tick(): Promise<void> {
    if (this.ticking) {
      this.tickAgain = true;
      return this.ticking;
    }
    this.ticking = (async () => {
      try {
        do {
          this.tickAgain = false;
          await this.schedule();
          await this.retryCleanup();
        } while (this.tickAgain);
      } catch (e) {
        console.error("orbit scheduler:", e);
      } finally {
        this.ticking = null;
      }
    })();
    return this.ticking;
  }

  private async schedule(): Promise<void> {
    const queued = this.store.queuedRuns();
    if (queued.length === 0) return;
    const res = await this.resources(true);
    for (const run of queued) {
      const leases = this.store.activeLeases();
      const a = allocate(run.spec.resources, res, leases);
      if (!a.ok) {
        if (run.reason !== a.reason) {
          run.reason = a.reason;
          this.save(run);
        }
        continue;
      }
      const lease: Lease = {
        id: `lease-${run.id}`,
        runId: run.id,
        node: this.node,
        gpuIds: a.gpuIds,
        cpus: run.spec.resources.cpus,
        memGB: run.spec.resources.memGB,
        state: "active",
        createdAt: nowIso(),
        releasedAt: null,
      };
      run.lease = lease;
      run.state = "starting";
      run.reason = null;
      this.store.tx(() => {
        this.store.putLease(lease);
        this.save(run, "leased", a.gpuIds.length ? `GPUs ${a.gpuIds.join(", ")}` : "no GPUs");
      });
      void this.launch(run.id);
    }
  }

  private async launch(id: string): Promise<void> {
    const ctl: { cancel?: "cancel" | "timeout"; logs?: ChildProcess } = {};
    this.active.set(id, ctl);
    let run = this.mustGet(id);
    const dirs = this.dirs(id);
    try {
      const image = await this.ensureImage(run, dirs);
      run = this.mustGet(id);
      run.image = image;
      if (ctl.cancel)
        return void (await this.finalize(run, "cancelled", null, "cancelled before start"));

      const containerId = await docker.startContainer(this.containerSpec(run, dirs, image));
      run = this.mustGet(id);
      run.containerId = containerId;
      run.state = "running";
      run.startedAt = nowIso();
      this.save(run, "started", `container ${containerId.slice(0, 12)}`);
      if (ctl.cancel) void docker.stopContainer(containerId);

      const st = await docker.inspectContainer(containerId);
      const want = [...(run.lease?.gpuIds ?? [])].sort().join(",");
      const got = [...(st?.gpuIds ?? [])].sort().join(",");
      if (want !== got) {
        this.requestStop(run, "cancel");
        throw new Error(`GPU mapping mismatch: leased [${want}] but container has [${got}]`);
      }
      if (run.spec.timeoutMin) {
        const t = setTimeout(
          () => this.requestStop(this.mustGet(id), "timeout"),
          run.spec.timeoutMin * 60_000,
        );
        t.unref();
      }
      await this.watch(id, containerId, true);
    } catch (e) {
      const msg = (e as Error).message;
      appendFileSync(dirs.log, `\n[orbit] ${msg}\n`);
      await this.finalize(this.mustGet(id), "failed", null, msg);
    } finally {
      this.active.delete(id);
    }
  }

  private async ensureImage(run: Run, dirs: RunDirs): Promise<string> {
    if (run.spec.image) return run.spec.image;
    const df = run.spec.dockerfile as string;
    const tag = docker.dockerfileTag(
      df,
      run.spec.project ? basename(run.spec.project) : basename(dirname(df)),
    );
    if (await docker.imageExists(tag)) {
      this.store.addEvent(run.id, "image", `reusing ${tag}`);
      return tag;
    }
    this.save(run, "build", `building ${tag}`);
    appendFileSync(dirs.log, `[orbit] docker build -f ${df} -t ${tag}\n`);
    const code = await docker.buildImage(df, dirname(df), tag, dirs.log);
    if (code !== 0) throw new Error(`docker build failed with exit code ${code}`);
    appendFileSync(dirs.log, "[orbit] build done\n");
    return tag;
  }

  private containerSpec(run: Run, dirs: RunDirs, image: string): docker.ContainerSpec {
    const s = run.spec;
    const mounts: docker.ContainerSpec["mounts"] = [
      { source: dirs.orbit, target: "/orbit", mode: "rw" },
    ];
    let workdir = "/orbit";
    if (run.code) {
      mounts.push({ source: dirs.workspace, target: "/workspace", mode: "rw" });
      workdir = join("/workspace", run.code.subdir);
    } else if (s.project) {
      mounts.push({ source: s.project, target: "/workspace", mode: "ro" });
      workdir = "/workspace";
    }
    mounts.push(...s.mounts);
    const env: Record<string, string> = {
      ...s.env,
      ORBIT_RUN_ID: run.id,
      ORBIT_OUTPUT: "/orbit/output",
      ORBIT_METRICS: "/orbit/metrics.jsonl",
      PYTHONUNBUFFERED: "1",
    };
    let user: string | null = null;
    if (!s.root) {
      const u = userInfo();
      user = `${u.uid}:${u.gid}`;
      env.HOME ??= "/tmp";
    }
    return {
      name: containerName(run.id),
      image,
      command: s.command,
      labels: { [docker.LABEL_RUN]: run.id, [docker.LABEL_HOME]: this.homeLabel },
      gpuIds: run.lease?.gpuIds ?? [],
      gpuMode: this.gpuMode,
      cpus: s.resources.cpus,
      memGB: s.resources.memGB,
      mounts,
      env,
      workdir,
      network: s.network,
      user,
    };
  }

  /** Follow logs and wait for exit, then collect and clean up. */
  private async watch(id: string, containerId: string, append: boolean): Promise<void> {
    const ctl = this.active.get(id) ?? {};
    this.active.set(id, ctl);
    const dirs = this.dirs(id);
    const logs = docker.followLogs(containerId, dirs.log, append);
    ctl.logs = logs;
    const drained = new Promise<boolean>((r) => logs.once("close", () => r(true)));
    const exitCode = await docker.waitContainer(containerId);
    // Evidence first: let the log follower reach EOF before the container is removed.
    const complete = await Promise.race([drained, sleep(LOG_DRAIN_TIMEOUT_MS).then(() => false)]);
    if (!complete) {
      logs.kill();
      appendFileSync(dirs.log, "\n[orbit] log collection timed out; log may be truncated\n");
      this.store.addEvent(id, "log", "log collection timed out; log may be truncated");
    }
    const st = await docker.inspectContainer(containerId);
    const run = this.mustGet(id);
    let state: RunState = exitCode === 0 ? "succeeded" : "failed";
    let reason = exitCode === 0 ? null : `exit code ${exitCode}`;
    if (st?.oomKilled) reason = `out of memory (limit ${run.spec.resources.memGB} GB)`;
    if (ctl.cancel === "cancel") {
      state = "cancelled";
      reason = "cancelled";
    } else if (ctl.cancel === "timeout") {
      state = "failed";
      reason = `timeout after ${run.spec.timeoutMin} min`;
    }
    await this.finalize(run, state, exitCode, reason);
  }

  private requestStop(run: Run, why: "cancel" | "timeout"): void {
    const ctl = this.active.get(run.id);
    if (ctl) ctl.cancel ??= why;
    this.store.addEvent(run.id, why, why === "cancel" ? "cancel requested" : "timeout reached");
    if (run.containerId) void docker.stopContainer(run.containerId);
  }

  /** Terminal transition: record the outcome, remove the container, release the lease. */
  private async finalize(
    run: Run,
    state: RunState,
    exitCode: number | null,
    reason: string | null,
  ): Promise<Run> {
    run.state = state;
    run.exitCode = exitCode;
    run.reason = reason;
    run.endedAt = nowIso();
    this.save(run, state, reason ?? (exitCode !== null ? `exit code ${exitCode}` : state));
    await this.cleanup(run);
    void this.tick();
    return this.mustGet(run.id);
  }

  private async cleanup(run: Run): Promise<void> {
    // By name as well: `docker run` can create the container and still fail before returning its id.
    const removed = await docker.removeContainer(run.containerId ?? containerName(run.id));
    const fresh = this.mustGet(run.id);
    if (!removed) {
      if (fresh.cleanup !== "failed") {
        fresh.cleanup = "failed";
        this.save(fresh, "cleanup", "container removal failed; lease kept until it succeeds");
      }
      return;
    }
    fresh.cleanup = "done";
    const lease = fresh.lease;
    this.store.tx(() => {
      if (lease && lease.state === "active") {
        lease.state = "released";
        lease.releasedAt = nowIso();
        this.store.putLease(lease);
      }
      this.save(fresh, "cleanup", lease ? "container removed, lease released" : "done");
    });
  }

  private async retryCleanup(): Promise<void> {
    for (const run of this.store.pendingCleanup()) {
      if (!this.active.has(run.id)) await this.cleanup(run);
    }
  }

  /** Reattach to runs that were active when the daemon last stopped. */
  private async recover(): Promise<void> {
    for (const run of this.store.listRuns({ states: ["starting", "running"], limit: 10_000 })) {
      const st = await docker.inspectContainer(run.containerId ?? containerName(run.id));
      if (!st) {
        await this.finalize(run, "lost", null, "container not found after daemon restart");
        continue;
      }
      if (!run.containerId || run.state === "starting") {
        run.containerId = st.id;
        run.state = "running";
        run.startedAt ??= nowIso();
      }
      this.save(
        run,
        "recovered",
        st.running ? "reattached after daemon restart" : "collected after daemon restart",
      );
      this.active.set(run.id, {});
      void this.watch(run.id, st.id, false).finally(() => this.active.delete(run.id));
    }
  }

  // ---- persistence ----

  private mustGet(id: string): Run {
    const r = this.store.getRun(id);
    if (!r) throw new NotFoundError(`run ${id} not found`);
    return r;
  }

  private save(run: Run, kind?: string, message?: string): void {
    this.store.putRun(run);
    const event = kind ? this.store.addEvent(run.id, kind, message ?? "") : undefined;
    this.emit("change", { run, event });
  }
}

const containerName = (runId: string) => `orbit-${runId}`;

export class UserError extends Error {}
export class NotFoundError extends Error {}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
