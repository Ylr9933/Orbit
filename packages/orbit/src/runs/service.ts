import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import {
  accessSync,
  appendFileSync,
  constants,
  cpSync,
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  truncateSync,
  writeFileSync,
} from "node:fs";
import { cp } from "node:fs/promises";
import { userInfo } from "node:os";
import { basename, delimiter, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { pipeline } from "node:stream/promises";
import type { AuthStore } from "../auth/index.ts";
import { type OrbitPaths, type RunDirs, runDirs } from "../config/paths.ts";
import {
  type AfterPhase,
  type AfterStatus,
  type AuthTestResult,
  type DoctorCheck,
  type DoctorReport,
  Folder,
  isTerminal,
  type Lease,
  leaseRequest,
  type NodeResources,
  type RemoteSubmit,
  type Run,
  type RunDeletion,
  type RunEvent,
  RunSpec,
  type RunSpecInput,
  type RunState,
  type ServiceSpec,
  serviceOrder,
} from "../contracts/index.ts";
import * as docker from "../executor/docker.ts";
import {
  containerPath,
  finishHarness,
  hostCli,
  type Prepared,
  prepareHarness,
} from "../harness/index.ts";
import { newId, nowIso } from "../lib/ids.ts";
import { Redactor } from "../lib/redact.ts";
import { dirBytes, safeJoin } from "../records/index.ts";
import { allocate, infeasible } from "../resources/allocate.ts";
import { diskCheck, lowFreeGB } from "../resources/disk.ts";
import { resolveAgentRef } from "../sessions/index.ts";
import type { RunFilter, Store } from "../store/index.ts";
import { bundleDir, isBundleHash } from "../workspace/bundle.ts";
import type { DatasetRegistry } from "../workspace/datasets.ts";
import { snapshotProject } from "../workspace/snapshot.ts";
import {
  type DispatchResult,
  joinReasons,
  nodeLeases,
  type RemoteNode,
  type RemotePlacement,
  remoteBlocker,
} from "./placement.ts";
import {
  dockerConfigDir,
  groupAlive,
  killGroup,
  procAlive,
  processEnv,
  procStart,
  readExitFile,
  SECRET_NAME,
  spawnProcess,
  writeShim,
} from "./process.ts";
import type { ShimConfig } from "./shim.ts";
import { cgroupOf, type Targets, UsageSampler } from "./usage.ts";

export interface RunServiceDeps {
  store: Store;
  paths: OrbitPaths;
  probe: () => Promise<NodeResources>;
  /** Credential profiles for `spec.auth`; runs with auth are rejected without it. */
  auth?: AuthStore;
  /** Named datasets on this node, for `dataset` mounts. */
  datasets?: DatasetRegistry;
  /** Scheduler period; the loop also runs after every submit/finish. */
  tickMs?: number;
  /**
   * Command prefix that runs this orbit binary (`node [execArgv] <entry>`); process runs get a
   * `docker` shim calling `<prefix> __docker-shim`. Without it process runs are rejected.
   */
  shim?: string[];
  /** Resource sampling period of running runs (default 5 s). */
  usageMs?: number;
}

export interface RunChange {
  run: Run;
  event?: RunEvent;
}

const PROBE_TTL_MS = 2000;
/** Group of the runs created by `testAuth`. */
export const AUTH_TEST_GROUP = "auth-test";
const LOG_DRAIN_TIMEOUT_MS = 15_000;
const STOP_GRACE_MS = 10_000;
const PROC_POLL_MS = 2000;
const REFUSAL_TTL_MS = 10 * 60_000;
const DOCKER_RETRY_MS = 5000;
/** Directory names too generic to name an image after (the task directory is used instead). */
const GENERIC_DIRS = new Set(["environment", "tests", "docker", "env", "verifier", "solution"]);

/**
 * The single owner of Run state on this node: submission, queueing, leases, container lifecycle,
 * evidence collection and cleanup. Emits "change" for every persisted update.
 */
export class RunService extends EventEmitter<{ change: [RunChange]; deleted: [string[]] }> {
  private readonly store: Store;
  private readonly paths: OrbitPaths;
  private readonly probeFn: () => Promise<NodeResources>;
  private readonly homeLabel: string;
  private readonly node: string;
  /** Worker nodes; set by the daemon when the cluster module starts. */
  private remote: RemotePlacement | null = null;
  /** `<run>@<node>` pairs whose node refused the run: not placed there again for a while. */
  private readonly refused = new Map<string, { why: string; until: number }>();
  /** Stops requested for local runs not watched yet (see `control`). */
  private readonly stopIntent = new Map<string, "cancel" | "timeout">();
  /** Resource samplers of the runs this node executes. */
  private readonly samplers = new Map<string, UsageSampler>();
  /** Runs from a primary still being received (see `submitRemote`). */
  private readonly receiving = new Map<string, Promise<Run>>();
  private readonly gpuMode = docker.detectGpuMode();
  private cached: { at: number; value: NodeResources } | null = null;
  private timer: NodeJS.Timeout | null = null;
  private ticking: Promise<void> | null = null;
  private tickAgain = false;
  private stopped = false;
  /** Runs with an active launch/watch task in this process. */
  private readonly active = new Map<string, Control>();

  private readonly deps: RunServiceDeps;

  constructor(deps: RunServiceDeps) {
    super();
    this.setMaxListeners(20);
    this.deps = deps;
    this.store = deps.store;
    this.paths = deps.paths;
    this.probeFn = deps.probe;
    this.node = deps.paths.node;
    this.homeLabel = createHash("sha256")
      .update(resolve(deps.paths.home))
      .digest("hex")
      .slice(0, 12);
  }

  // ---- public API ----

  async start(): Promise<void> {
    await this.recover();
    void this.measureMissing();
    this.timer = setInterval(() => void this.tick(), this.deps.tickMs ?? 3000);
    void this.tick();
  }

  /** This node's name in the cluster. */
  get nodeName(): string {
    return this.node;
  }

  setRemote(remote: RemotePlacement | null): void {
    this.remote = remote;
  }

  private remoteNodes(): RemoteNode[] {
    return [...(this.remote?.nodes() ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  }

  async stop(): Promise<void> {
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    await this.ticking;
    for (const a of this.active.values()) {
      a.logs?.kill();
      clearTimeout(a.timeout);
    }
    for (const u of this.samplers.values()) u.halt();
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

  /**
   * Why a run cannot be deleted, or null. Only finished runs whose cleanup is confirmed (and, for a
   * mirror of a remote run, whose mirroring is over); runs of a bench trial go with their job.
   */
  deleteBlocker(run: Run, forJob = false): string | null {
    if (!isTerminal(run.state))
      return `${run.id} is ${run.state}; cancel it and wait for it to end`;
    if (run.cleanup !== "done")
      return `${run.id}: cleanup is ${run.cleanup}; its container or processes may still exist`;
    if (this.active.has(run.id)) return `${run.id} is still being finalized`;
    if (run.remote && this.store.getSync(run.id)?.done === false)
      return `${run.id} is still being mirrored from ${run.node}`;
    if (!forJob) {
      const t = this.store.trialByRun(run.id);
      if (t) return `${run.id} belongs to bench job ${t.jobId}; delete the job instead`;
    }
    return null;
  }

  /**
   * Delete finished runs: their records, events and leases, and their directory (logs, outputs,
   * code snapshot, Agent home). All are checked before anything is removed. Irreversible.
   */
  async delete(ids: string[], opts: { forJob?: boolean } = {}): Promise<RunDeletion> {
    const unique = [...new Set(ids)];
    const runs = unique.map((id) => {
      const r = this.store.getRun(id);
      if (!r) throw new NotFoundError(`run not found: ${id}`);
      return r;
    });
    const blocked = runs.map((r) => this.deleteBlocker(r, opts.forJob)).filter(Boolean);
    if (blocked.length) throw new UserError(blocked.join("; "));
    this.store.deleteRuns(unique);
    const leftovers: string[] = [];
    for (const r of runs) if (!(await this.removeDir(r))) leftovers.push(this.dirs(r.id).root);
    this.emit("deleted", unique);
    return { deleted: unique, leftovers };
  }

  /** Remove a run directory; files a container wrote as root are removed from a container. */
  private async removeDir(run: Run): Promise<boolean> {
    const root = this.dirs(run.id).root;
    const rm = () => {
      try {
        rmSync(root, { recursive: true, force: true });
        return true;
      } catch {
        return false;
      }
    };
    if (rm()) return true;
    const image = run.image ?? run.spec.image;
    if (image && (await docker.imageExists(image).catch(() => false)))
      await docker.emptyDirAsRoot(root, image);
    return rm();
  }

  storeList(filter: RunFilter): Run[] {
    return this.store.listRuns(filter);
  }

  events(id: string, afterSeq = 0): RunEvent[] {
    return this.store.events(id, afterSeq);
  }

  async submit(input: RunSpecInput, opts: { folder?: string } = {}): Promise<Run> {
    const spec = RunSpec.parse(input);
    const folder = Folder.safeParse(opts.folder ?? "");
    if (!folder.success) throw new UserError(folder.error.issues[0]?.message ?? "invalid folder");
    const failed = (await this.preflight(spec)).find((c) => !c.ok);
    if (failed) throw new UserError(failed.detail);
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
      proc: null,
      cleanup: "pending",
      remote: false,
      origin: null,
      imageId: null,
      note: "",
      folder: folder.data,
      usage: null,
      services: [],
      after: null,
      sizeBytes: null,
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
    if (code?.skippedSubmodules.length) {
      const event = this.store.addEvent(
        run.id,
        "warning",
        `submodule contents are not snapshotted: ${code.skippedSubmodules.join(", ")}`,
      );
      this.changed(run, event);
    }
    void this.tick();
    return run;
  }

  async cancel(id: string): Promise<Run> {
    const run = this.mustGet(id);
    if (isTerminal(run.state)) return run;
    if (run.state === "queued") {
      return this.finalize(run, "cancelled", null, "cancelled while queued");
    }
    if (run.remote) {
      const sync = this.store.getSync(id);
      if (sync) this.store.putSync({ ...sync, cancel: true });
      const event = this.store.addEvent(id, "cancel", `cancel requested on ${run.node}`);
      this.changed(run, event);
      void this.remote?.cancel(run).catch(() => {});
      return this.mustGet(id);
    }
    this.requestStop(run, "cancel");
    return this.mustGet(id);
  }

  /** Resolves with the run once it is terminal and cleaned up (or failed to clean up). */
  waitDone(id: string): Promise<Run> {
    const settled = (r: Run) => isTerminal(r.state) && r.cleanup !== "pending";
    const now = this.mustGet(id);
    if (settled(now)) return Promise.resolve(now);
    return new Promise((resolve) => {
      const onChange = ({ run }: RunChange) => {
        if (run.id !== id || !settled(run)) return;
        this.off("change", onChange);
        resolve(run);
      };
      this.on("change", onChange);
    });
  }

  /**
   * Check a profile end to end: a small real run asks the Agent for a fixed answer. The answer is not in
   * the prompt, so finding it in the log means the model replied.
   */
  async testAuth(name: string, image = "python:3.12-slim"): Promise<AuthTestResult> {
    const entry = this.deps.auth?.get(name);
    if (!entry) throw new NotFoundError(`auth profile not found: ${name}`);
    const prompt =
      "Reply with the word ORBIT_AUTH immediately followed by _OK, as one token, and nothing else.";
    const command =
      entry.profile.harness === "codex"
        ? [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
          ]
        : ["claude", "-p", "--dangerously-skip-permissions", prompt];
    const run = await this.submit({
      name: `auth-test ${name}`,
      group: AUTH_TEST_GROUP,
      image,
      command,
      auth: name,
      snapshot: false,
      resources: { gpus: 0, cpus: 1, memGB: 2, node: this.node },
      timeoutMin: 5,
      tags: { auth: name },
    });
    const done = await this.waitDone(run.id);
    const log = readFileSync(this.dirs(run.id).log, "utf8");
    const ok = done.state === "succeeded" && log.includes("ORBIT_AUTH_OK");
    const tail = log.trim().split("\n").slice(-5).join("\n");
    return {
      ok,
      runId: run.id,
      detail: ok
        ? "agent replied ORBIT_AUTH_OK"
        : `${done.state}: ${done.reason ?? ""}\n${tail}`.trim(),
    };
  }

  /** File runs in a folder (`""` for none); returns the runs that changed. */
  setFolder(ids: string[], folder: string): Run[] {
    const runs = ids.map((id) => this.mustGet(id));
    const changed = runs.filter((r) => r.folder !== folder);
    for (const r of changed) {
      r.folder = folder;
      this.save(r, "folder", folder || "(none)");
    }
    return changed;
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

  /**
   * Check a run before submitting it: the same validation as `submit`, plus (as `full`) whether the
   * image and datasets are there, the output disk has room, and where and when it would start.
   */
  async check(input: RunSpecInput): Promise<DoctorReport> {
    const checks = await this.preflight(RunSpec.parse(input), true);
    return { ok: checks.every((c) => c.ok), checks };
  }

  /** Why `spec` is invalid on this daemon, or null. Resolves `spec.dockerfile` and host networking. */
  private specError(spec: RunSpec): string | null {
    if (spec.project && !isAbsolute(spec.project)) return "project must be an absolute path";
    if (spec.project && !statSync(spec.project, { throwIfNoEntry: false })?.isDirectory())
      return `project not found: ${spec.project}`;
    if (spec.backend === "process") {
      if (!this.deps.shim) return "process runs are not available in this daemon";
      if (spec.cwd && (!isAbsolute(spec.cwd) || !existsSync(spec.cwd)))
        return `cwd not found: ${spec.cwd}`;
      if (spec.mounts.length > 0 || spec.collect.length > 0 || spec.workdir || spec.mkdirs.length)
        return "mounts, collect, mkdirs and workdir apply to docker runs only";
    }
    if (spec.agentBundle) {
      if (!spec.auth) return "agentBundle needs an auth profile";
      if (
        !isAbsolute(spec.agentBundle) ||
        !statSync(spec.agentBundle, { throwIfNoEntry: false })?.isDirectory()
      )
        return `agentBundle directory not found: ${spec.agentBundle}`;
    }
    for (const m of spec.mounts) {
      if (m.source && (!isAbsolute(m.source) || !existsSync(m.source)))
        return `mount source not found: ${m.source}`;
    }
    if (spec.dockerfile) {
      const df = isAbsolute(spec.dockerfile)
        ? spec.dockerfile
        : resolve(spec.project ?? "/", spec.dockerfile);
      if (!existsSync(df)) return `dockerfile not found: ${df}`;
      spec.dockerfile = df;
    }
    for (const s of spec.services) {
      for (const p of [s.dockerfile, s.context])
        if (p && (!isAbsolute(p) || !existsSync(p)))
          return `service ${s.name}: ${p} not found (absolute paths only)`;
    }
    // A node's own auth profile decides host networking; a worker applies its own on arrival.
    if (spec.auth && this.deps.auth?.get(spec.auth)?.profile.hostNetwork) spec.hostNetwork = true;
    if (spec.hostNetwork && !spec.network) return "host network conflicts with network disabled";
    return null;
  }

  private async preflight(spec: RunSpec, full = false): Promise<DoctorCheck[]> {
    const checks: DoctorCheck[] = [];
    const add = (name: string, ok: boolean, detail: string, warn = false) =>
      checks.push({ name, ok, warn, detail });
    const invalid = this.specError(spec);
    if (invalid) {
      add("spec", false, invalid);
      return checks;
    }
    const nodes = this.remoteNodes();
    if (full) {
      if (spec.project)
        add("project", true, `${spec.project} (${spec.snapshot ? "snapshot" : "read-only mount"})`);
      if (spec.backend === "docker") {
        if (spec.dockerfile) add("image", true, `built from ${spec.dockerfile}`);
        else if (spec.image) {
          const have = await docker.imageExists(spec.image);
          add(
            "image",
            true,
            have
              ? `${spec.image} (on this node)`
              : `${spec.image} not on this node; pulled at start`,
            !have,
          );
        }
      }
      for (const m of spec.mounts) {
        const name = `mount ${m.target}`;
        if (m.source) add(name, true, `${m.source} (${m.mode})`);
        else if (m.dataset) {
          const local = this.deps.datasets?.path(m.dataset);
          const where = [
            ...(local ? [`${this.node}:${local}`] : []),
            ...nodes.filter((n) => n.datasets.includes(m.dataset as string)).map((n) => n.name),
          ];
          if (local && !existsSync(local))
            add(name, false, `dataset ${m.dataset}: ${local} is registered but missing`);
          else if (where.length === 0)
            add(name, false, `dataset ${m.dataset} is not registered on any node`);
          else add(name, true, `dataset ${m.dataset} (${m.mode}) on ${where.join(", ")}`);
        }
      }
      const out = await diskCheck(
        "output",
        this.paths.runs,
        "move runs to a large disk with `orbit config data <dir>`",
      );
      try {
        accessSync(this.paths.runs, constants.W_OK);
      } catch {
        Object.assign(out, { ok: false, detail: `${this.paths.runs} is not writable` });
      }
      checks.push(out);
    }
    const local = await this.localBlocker(spec);
    const reasons: [string, string][] = local ? [[this.node, local]] : [];
    const candidates = nodes.filter((n) => {
      const why = remoteBlocker(spec, n);
      if (why) reasons.push([n.name, why]);
      return !why;
    });
    if (local && candidates.length === 0) add("placement", false, joinReasons(reasons));
    else if (full) checks.push(await this.startCheck(spec, local === null, candidates));
    return checks;
  }

  /** Where the run would start if submitted now (runs already queued may go first). */
  private async startCheck(
    spec: RunSpec,
    here: boolean,
    candidates: RemoteNode[],
  ): Promise<DoctorCheck> {
    const waits: [string, string][] = [];
    const ahead = this.store.queuedRuns().length;
    const queue = ahead ? `; ${ahead} run(s) already queued may go first` : "";
    if (here) {
      const a = allocate(leaseRequest(spec), await this.resources(true), this.store.activeLeases());
      if (a.ok)
        return {
          name: "placement",
          ok: true,
          warn: false,
          detail: `starts now on ${this.node}${a.gpuIds.length ? ` with ${a.gpuIds.length} GPU(s)` : ""}${queue}`,
        };
      waits.push([this.node, a.reason]);
    }
    const mirrors = candidates.length ? this.mirrors() : [];
    for (const n of candidates) {
      if (!n.online) {
        waits.push([n.name, "offline"]);
        continue;
      }
      const r = n.resources as NodeResources;
      const a = allocate(leaseRequest(spec), r, nodeLeases(n, mirrors));
      if (!a.ok) {
        waits.push([n.name, a.reason]);
        continue;
      }
      const low = r.disk.freeGB < lowFreeGB(r.disk.totalGB);
      return {
        name: "placement",
        ok: true,
        warn: low,
        detail: `starts now on ${n.name}${low ? ` (its data disk has ${Math.round(r.disk.freeGB)} GB free)` : ""}${queue}`,
      };
    }
    return { name: "placement", ok: true, warn: true, detail: `queues: ${joinReasons(waits)}` };
  }

  /** Why `spec` can never run on this node as configured now, or null. */
  private async localBlocker(spec: RunSpec): Promise<string | null> {
    if (spec.resources.node && spec.resources.node !== this.node)
      return `pinned to ${spec.resources.node}`;
    for (const m of spec.mounts)
      if (m.dataset && !this.deps.datasets?.path(m.dataset))
        return `dataset ${m.dataset} not registered on this node`;
    if (spec.auth) {
      const entry = this.deps.auth?.get(spec.auth);
      if (!entry) return `auth profile not found: ${spec.auth}`;
      if (!(await hostCli(entry.profile.harness)))
        return `${entry.profile.harness} CLI not found on this node`;
    }
    return infeasible(leaseRequest(spec), await this.resources());
  }

  /**
   * Place queued runs: on this node when it can run them now, else on the first worker node (by
   * name) that can. Runs received from a primary stay here.
   */
  private async schedule(): Promise<void> {
    const queued = this.store.queuedRuns();
    if (queued.length === 0) return;
    // A copy: memory granted in this pass is taken off what the probe saw as available.
    const res = structuredClone(await this.resources(true));
    const nodes = this.remoteNodes();
    const mirrors = nodes.length ? this.mirrors() : [];
    for (const q of queued) {
      const reasons: [string, string][] = [];
      const blocked = await this.localBlocker(q.spec);
      // Re-read after the awaits: a cancel may have ended the run meanwhile. No await from here on
      // until it is leased, placed or its reason saved.
      const run = this.store.getRun(q.id);
      if (run?.state !== "queued") continue;
      if (blocked) reasons.push([this.node, blocked]);
      else {
        const a = allocate(leaseRequest(run.spec), res, this.store.activeLeases());
        if (a.ok) {
          this.leaseLocal(run, a.gpuIds);
          res.memory.availableGB -= leaseRequest(run.spec).memGB;
          continue;
        }
        reasons.push([this.node, a.reason]);
      }
      let placed = false;
      for (const n of run.origin ? [] : nodes) {
        const why =
          this.refusal(`${run.id}@${n.name}`) ??
          remoteBlocker(run.spec, n) ??
          (n.online ? null : "offline");
        if (why) {
          reasons.push([n.name, why]);
          continue;
        }
        const a = allocate(
          leaseRequest(run.spec),
          n.resources as NodeResources,
          nodeLeases(n, mirrors),
        );
        if (!a.ok) {
          reasons.push([n.name, a.reason]);
          continue;
        }
        mirrors.push(this.placeRemote(run, n.name, a.gpuIds));
        placed = true;
        break;
      }
      if (placed) continue;
      const reason = joinReasons(reasons);
      if (run.reason !== reason) {
        run.reason = reason;
        this.save(run);
      }
    }
  }

  private refusal(key: string): string | null {
    const r = this.refused.get(key);
    if (r && r.until > Date.now()) return r.why;
    this.refused.delete(key);
    return null;
  }

  private leaseLocal(run: Run, gpuIds: string[]): void {
    const lease: Lease = {
      id: `lease-${run.id}`,
      runId: run.id,
      node: this.node,
      gpuIds,
      cpus: leaseRequest(run.spec).cpus,
      memGB: leaseRequest(run.spec).memGB,
      state: "active",
      createdAt: nowIso(),
      releasedAt: null,
    };
    run.lease = lease;
    run.state = "starting";
    run.reason = null;
    this.store.tx(() => {
      this.store.putLease(lease);
      this.save(run, "leased", gpuIds.length ? `GPUs ${gpuIds.join(", ")}` : "no GPUs");
    });
    void this.launch(run.id).catch((e) =>
      console.error(`orbit: run ${run.id}:`, (e as Error).message),
    );
  }

  // ---- runs on other nodes (primary side) ----

  /** Non-terminal runs this node placed on workers. */
  private mirrors(): Run[] {
    return this.store
      .listRuns({ states: ["starting", "running"], limit: 100_000 })
      .filter((r) => r.remote);
  }

  /**
   * Mark the run as placed on `node` with a predicted lease (kept in the run record only; it counts
   * against that node until the node reports its own lease) and send it.
   */
  private placeRemote(run: Run, node: string, gpuIds: string[]): Run {
    run.state = "starting";
    run.remote = true;
    run.node = node;
    run.reason = null;
    run.lease = {
      id: `lease-${run.id}`,
      runId: run.id,
      node,
      gpuIds,
      cpus: leaseRequest(run.spec).cpus,
      memGB: leaseRequest(run.spec).memGB,
      state: "active",
      createdAt: nowIso(),
      releasedAt: null,
    };
    this.store.tx(() => {
      this.store.putSync({
        runId: run.id,
        node,
        eventSeq: 0,
        confirmed: false,
        cancel: false,
        done: false,
      });
      this.save(run, "placed", `node ${node}${gpuIds.length ? `, GPUs ${gpuIds.join(", ")}` : ""}`);
    });
    void this.dispatchRemote(run.id);
    return run;
  }

  private async dispatchRemote(id: string): Promise<void> {
    const run = this.mustGet(id);
    const remote = this.remote;
    const r: DispatchResult = remote
      ? await remote
          .dispatch(run)
          .catch((e) => ({ ok: false, kind: "unknown", message: (e as Error).message }) as const)
      : { ok: false, kind: "unreachable", message: "cluster not running" };
    const sync = this.store.getSync(id);
    if (!sync) return;
    // The node was removed while the run was being sent: it may run there, untracked.
    if (sync.done && (r.ok || r.kind === "unknown")) {
      this.loseRemote(id, `node ${run.node} was removed`);
      return;
    }
    if (r.ok) {
      this.store.putSync({ ...sync, confirmed: true });
      this.store.addEvent(id, "dispatched", `accepted by ${run.node}`);
      if (sync.cancel) void remote?.cancel(run).catch(() => {});
      return;
    }
    if (r.kind === "unknown") {
      this.store.addEvent(id, "dispatch", `${r.message}; checking with ${run.node}`);
      return;
    }
    if (r.kind === "rejected")
      this.refused.set(`${id}@${run.node}`, {
        why: `refused: ${r.message}`,
        until: Date.now() + REFUSAL_TTL_MS,
      });
    this.requeueRemote(id, `${run.node}: ${r.message}`);
  }

  /** The run never started on its node: queue it here again (or finish a requested cancel). */
  requeueRemote(id: string, why: string): void {
    const run = this.mustGet(id);
    if (!run.remote || isTerminal(run.state)) return;
    const sync = this.store.getSync(id);
    this.store.deleteSync(id);
    const cancelled = sync?.cancel ?? false;
    run.remote = false;
    run.node = this.node;
    run.lease = null;
    run.state = cancelled ? "cancelled" : "queued";
    run.reason = cancelled ? "cancelled" : why;
    if (cancelled) {
      run.endedAt = nowIso();
      run.cleanup = "done";
    }
    this.save(run, cancelled ? "cancelled" : "requeued", why);
    void this.tick();
  }

  /** The node no longer knows a run it had accepted, or the node was removed. */
  loseRemote(id: string, why: string): void {
    const run = this.mustGet(id);
    const sync = this.store.getSync(id);
    if (sync) this.store.putSync({ ...sync, done: true });
    if (!run.remote || isTerminal(run.state)) return;
    run.state = "lost";
    run.reason = why;
    run.endedAt = nowIso();
    run.cleanup = "done";
    if (run.lease?.state === "active")
      run.lease = { ...run.lease, state: "released", releasedAt: nowIso() };
    this.save(run, "lost", why);
    void this.tick();
  }

  /**
   * Mirror the worker's record of a run: its new events (with their original times), state, outcome,
   * container and cleanup. Emits "change" per event so notifications and benchmarks see the
   * terminal event as for a local run.
   */
  applyRemote(id: string, remote: Run, events: RunEvent[]): Run {
    const run = this.mustGet(id);
    const sync = this.store.getSync(id);
    // Lost or requeued meanwhile (node removed, run unknown there): keep the local outcome.
    if (!run.remote || !sync || sync.done) return run;
    const queuedThere = remote.state === "queued";
    run.state = queuedThere ? "starting" : remote.state;
    run.reason = queuedThere ? `queued on ${run.node}: ${remote.reason ?? ""}` : remote.reason;
    run.exitCode = remote.exitCode;
    run.image = remote.image ?? run.image;
    run.imageId = remote.imageId ?? run.imageId;
    run.containerId = remote.containerId;
    run.startedAt = remote.startedAt;
    run.endedAt = remote.endedAt;
    run.cleanup = remote.cleanup;
    run.usage = remote.usage;
    if (remote.lease) run.lease = remote.lease;
    else if (isTerminal(remote.state) && run.lease?.state === "active")
      run.lease = { ...run.lease, state: "released", releasedAt: remote.endedAt ?? nowIso() };
    const fresh = events.filter((e) => e.seq > (sync?.eventSeq ?? 0));
    const saved = this.store.tx(() => {
      this.store.putRun(run);
      const out = fresh.map((e) => this.store.addEvent(id, e.kind, e.message, e.at));
      this.store.putSync({
        ...sync,
        confirmed: true,
        eventSeq: fresh.at(-1)?.seq ?? sync.eventSeq,
        cancel: sync.cancel && !isTerminal(remote.state),
      });
      return out;
    });
    if (saved.length === 0) this.changed(run);
    for (const event of saved) this.changed(run, event);
    if (isTerminal(run.state)) void this.tick();
    return run;
  }

  // ---- runs from a primary (worker side) ----

  /**
   * Accept a run placed here by another node. Idempotent by id. Its code arrives as bundles already
   * stored under `cache/bundles`; secrets, datasets and auth come from this node's own configuration.
   */
  submitRemote(input: RemoteSubmit): Promise<Run> {
    // A retried submission while the first is still being received joins it.
    const pending = this.receiving.get(input.id);
    if (pending) return pending;
    const p = this.receiveRemote(input).finally(() => this.receiving.delete(input.id));
    this.receiving.set(input.id, p);
    return p;
  }

  private async receiveRemote(input: RemoteSubmit): Promise<Run> {
    const existing = this.store.getRun(input.id);
    if (existing) {
      if (existing.origin !== input.origin)
        throw new UserError(`run ${input.id} already exists on ${this.node}`);
      return existing;
    }
    const spec = RunSpec.parse(input.spec);
    if (spec.backend !== "docker") throw new UserError("only docker runs can run on another node");
    if (spec.mounts.some((m) => m.source)) throw new UserError("host path mounts are not portable");
    if (spec.project && !input.workspace)
      throw new UserError("a project run needs its code snapshot");
    const bundle = (hash: string) => {
      if (!isBundleHash(hash)) throw new UserError(`bad bundle hash: ${hash}`);
      const dir = bundleDir(this.paths.bundles, hash);
      if (!existsSync(dir)) throw new UserError(`bundle ${hash.slice(0, 12)} not uploaded`);
      return dir;
    };
    spec.resources.node = this.node;
    delete spec.agent;
    if (input.dockerfile) {
      const df = safeJoin(bundle(input.dockerfile.bundle), input.dockerfile.path);
      if (!df || !existsSync(df)) throw new UserError("dockerfile missing from its bundle");
      spec.dockerfile = df;
    }
    if (input.agentBundle) spec.agentBundle = bundle(input.agentBundle);
    if (spec.auth && this.deps.auth?.get(spec.auth)?.profile.hostNetwork) spec.hostNetwork = true;
    const why = await this.localBlocker(spec);
    if (why) throw new UserError(why);
    const workspace = input.workspace ? bundle(input.workspace) : null;

    const dirs = runDirs(this.paths, input.id);
    mkdirSync(dirs.output, { recursive: true });
    writeFileSync(dirs.metrics, "");
    writeFileSync(dirs.log, "");
    // Asynchronously: a large snapshot must not stall heartbeats and other requests.
    if (workspace) await cp(workspace, dirs.workspace, { recursive: true, verbatimSymlinks: true });
    const run: Run = {
      id: input.id,
      spec,
      state: "queued",
      reason: null,
      exitCode: null,
      node: this.node,
      image: spec.image ?? null,
      containerId: null,
      lease: null,
      code: input.code,
      proc: null,
      cleanup: "pending",
      remote: false,
      origin: input.origin,
      imageId: null,
      note: "",
      folder: "",
      usage: null,
      services: [],
      after: null,
      sizeBytes: null,
      createdAt: nowIso(),
      startedAt: null,
      endedAt: null,
    };
    this.save(run, "submitted", `from ${input.origin}`);
    void this.tick();
    return run;
  }

  private async launch(id: string): Promise<void> {
    const ctl: Control = {};
    this.active.set(id, ctl);
    let run = this.mustGet(id);
    const dirs = this.dirs(id);
    const envFile = this.envFile(id);
    if (run.spec.backend === "process") return this.launchProcess(run, dirs, ctl);
    try {
      const image = await this.ensureImage(run, dirs);
      const imageId = await docker.imageId(image);
      run = this.mustGet(id);
      if (ctl.cancel)
        return void (await this.finalize(run, "cancelled", null, "cancelled before start"));

      const spec = this.containerSpec(run, dirs, image);
      if (keepsContainer(run.spec)) writePhaseScript(join(dirs.orbit, "phases"));
      if (usesRunNetworks(run.spec)) {
        // Before the run's container: a failure here is the environment's, not the method's.
        await this.startServices(id, dirs, ctl);
        if (ctl.cancel)
          return void (await this.finalize(
            this.mustGet(id),
            "cancelled",
            null,
            "cancelled before start",
          ));
        run = this.mustGet(id);
        spec.networks = this.networkNames(run)
          .filter((n) => run.spec.runNetworks.includes(n.short))
          .map((n) => ({ name: n.name, aliases: ["main"] }));
      }
      const secretEnv = this.passEnv(run);
      if (run.spec.auth) {
        const h = await this.prepareAuth(run, dirs);
        h.env.PATH = containerPath(
          h.cli.pathDirs,
          run.spec.env.PATH ?? (await docker.imagePath(image)),
        );
        spec.mounts.push(...h.mounts);
        Object.assign(spec.env, h.env);
        Object.assign(secretEnv, h.secretEnv);
      }
      if (Object.keys(secretEnv).length > 0) {
        writeFileSync(envFile, docker.envFileText(secretEnv), { mode: 0o600 });
        spec.envFile = envFile;
      }
      const containerId = await docker
        .startContainer(spec)
        .finally(() => rmSync(envFile, { force: true }));
      run = this.mustGet(id);
      run.image = image;
      run.imageId = imageId;
      run.containerId = containerId;
      run.state = "running";
      run.startedAt = nowIso();
      this.save(run, "started", `container ${containerId.slice(0, 12)}`);
      if (ctl.cancel) void docker.stopContainer(containerId);

      const st = await docker.inspectContainer(containerId);
      const want = [...(run.lease?.gpuIds ?? [])].sort().join(",");
      const got = [...(st?.gpuIds ?? [])].sort().join(",");
      if (want !== got) {
        // Stop it, then collect logs and outputs as for any failure before the container goes.
        ctl.fail = `GPU mapping mismatch: leased [${want}] but container has [${got}]`;
        appendFileSync(dirs.log, `[orbit] ${ctl.fail}\n`);
        void docker.stopContainer(containerId);
      } else this.armTimeout(run);
      await this.watch(id, containerId, false);
    } catch (e) {
      const msg = (e as Error).message;
      appendFileSync(dirs.log, `\n[orbit] ${this.redactor(run).apply(msg)}\n`);
      await this.finalize(this.mustGet(id), "failed", null, msg);
    } finally {
      this.active.delete(id);
    }
  }

  private envFile(id: string): string {
    return join(this.paths.tmp, `${id}.env`);
  }

  /** `spec.passEnv` values from the daemon environment; missing variables are skipped. */
  private passEnv(run: Run): Record<string, string> {
    const out: Record<string, string> = {};
    for (const k of run.spec.passEnv) {
      const v = process.env[k];
      if (v !== undefined) out[k] = v;
      else this.store.addEvent(run.id, "env", `${k} is not set in the daemon environment`);
    }
    return out;
  }

  /** Stop the run when its timeout is reached (from `startedAt`, so also after a restart). */
  private armTimeout(run: Run): void {
    if (!run.spec.timeoutMin || this.stopped) return;
    this.disarmTimeout(run.id);
    const ctl = this.control(run.id);
    const started = run.startedAt ? Date.parse(run.startedAt) : Date.now();
    const left = Math.max(0, started + run.spec.timeoutMin * 60_000 - Date.now());
    const t = setTimeout(() => {
      const now = this.store.getRun(run.id);
      if (now && !isTerminal(now.state)) this.requestStop(now, "timeout");
    }, left);
    ctl.timeout = t;
    t.unref();
  }

  private disarmTimeout(id: string): void {
    const ctl = this.active.get(id);
    if (!ctl) return;
    clearTimeout(ctl.timeout);
    ctl.timeout = undefined;
  }

  /** A run's networks: `default` (internal when the run has no network) plus declared ones. */
  private networkNames(run: Run): { short: string; name: string; internal: boolean }[] {
    const declared = run.spec.networks.some((n) => n.name === "default")
      ? run.spec.networks
      : [{ name: "default", internal: !run.spec.network }, ...run.spec.networks];
    return declared.map((n) => ({
      short: n.name,
      name: `orbit-${run.id}-${n.name}`,
      internal: n.internal,
    }));
  }

  /**
   * Build or pull the service images, create the run's networks, then start the services in
   * dependency order, each once its dependencies are ready, and wait for the run's own dependencies.
   * Throws on any failure; `cleanup` removes whatever was created.
   */
  private async startServices(id: string, dirs: RunDirs, ctl: Control): Promise<void> {
    let run = this.mustGet(id);
    const images = new Map<string, string>();
    for (const s of run.spec.services) {
      if (ctl.cancel) return;
      images.set(s.name, await this.serviceImage(run, dirs, s));
    }
    const labels = { [docker.LABEL_PARENT]: id, [docker.LABEL_HOME]: this.homeLabel };
    for (const n of this.networkNames(run)) {
      const err = await docker.createNetwork(n.name, n.internal, labels);
      if (err) throw new Error(`network ${n.short}: ${err}`);
    }
    for (const s of serviceOrder(run.spec.services) ?? []) {
      if (ctl.cancel) return;
      await this.waitServices(id, s.dependsOn, ctl);
      const spec = this.serviceContainer(run, s, images.get(s.name) as string);
      let containerId: string;
      try {
        containerId = await docker.startContainer(spec);
      } catch (e) {
        throw new Error(`service ${s.name}: ${(e as Error).message}`);
      }
      run = this.mustGet(id);
      run.services.push({ name: s.name, containerId, failure: null });
      this.save(run, "service", `${s.name} started (${containerId.slice(0, 12)})`);
    }
    await this.waitServices(id, run.spec.dependsOn, ctl);
  }

  /** Wait until each service is healthy (with a health check) or running (without one). */
  private async waitServices(id: string, names: string[], ctl: Control): Promise<void> {
    for (const name of names) {
      const s = this.mustGet(id).spec.services.find((x) => x.name === name) as ServiceSpec;
      const containerId = this.mustGet(id).services.find((x) => x.name === name)?.containerId;
      if (!containerId) throw new Error(`service ${name} was not started`);
      // Docker gives up on its own after start period + retries × interval; the cap is a fallback.
      const h = s.healthcheck;
      const capMs = h
        ? (h.startPeriodSec + (h.retries + 1) * (h.intervalSec + h.timeoutSec)) * 1000 + 60_000
        : 60_000;
      const deadline = Date.now() + capMs;
      for (;;) {
        if (ctl.cancel) return;
        const st = await docker.inspectContainer(containerId);
        if (!st || !st.running) {
          const why = st
            ? `exited with code ${st.exitCode}${st.oomKilled ? " (out of memory)" : ""}`
            : "is gone";
          throw new Error(`service ${name} ${why}`);
        }
        if (!h || st.health === "healthy") break;
        if (st.health === "unhealthy") throw new Error(`service ${name} is unhealthy`);
        if (Date.now() > deadline) throw new Error(`service ${name} did not become healthy`);
        await sleep(1000);
      }
      this.store.addEvent(id, "service", `${name} ${h ? "healthy" : "running"}`);
    }
  }

  private async serviceImage(run: Run, dirs: RunDirs, s: ServiceSpec): Promise<string> {
    if (s.image) {
      if (await docker.imageExists(s.image)) return s.image;
      this.store.addEvent(run.id, "pull", `service ${s.name}: pulling ${s.image}`);
      const code = await docker.pullImage(s.image, dirs.log);
      if (code !== 0) throw new Error(`service ${s.name}: docker pull ${s.image} failed`);
      return s.image;
    }
    const df = s.dockerfile as string;
    const context = s.context ?? dirname(df);
    const tag = docker.dockerfileTag(df, context, `${basename(context)}-${s.name}`);
    if (await docker.imageExists(tag)) {
      this.store.addEvent(run.id, "image", `service ${s.name}: reusing ${tag}`);
      return tag;
    }
    this.store.addEvent(run.id, "build", `service ${s.name}: building ${tag}`);
    appendFileSync(
      dirs.log,
      `[orbit] service ${s.name}: docker build -f ${df} -t ${tag} ${context}\n`,
    );
    const code = await docker.buildImage(df, context, tag, dirs.log);
    if (code !== 0)
      throw new Error(`service ${s.name}: docker build failed with exit code ${code}`);
    return tag;
  }

  private serviceContainer(run: Run, s: ServiceSpec, image: string): docker.ContainerSpec {
    const nets = this.networkNames(run);
    return {
      name: `${containerName(run.id)}-${s.name}`,
      image,
      command: s.command ?? [],
      labels: { [docker.LABEL_PARENT]: run.id, [docker.LABEL_HOME]: this.homeLabel },
      gpuIds: [],
      gpuMode: this.gpuMode,
      cpus: s.cpus ?? null,
      memGB: s.memGB ?? null,
      mounts: [],
      env: s.env,
      workdir: s.workdir ?? null,
      network: "bridge",
      networks: nets
        .filter((n) => s.networks.includes(n.short))
        .map((n) => ({ name: n.name, aliases: [s.name] })),
      user: null,
      init: s.init,
      shm: false,
      ...(s.shmGB ? { shmGB: s.shmGB } : {}),
      ...(s.healthcheck ? { healthcheck: s.healthcheck } : {}),
      readOnly: s.readOnly,
      tmpfs: s.tmpfs,
      capAdd: s.capAdd,
      capDrop: s.capDrop,
      securityOpt: s.securityOpt,
      ...(s.pidsLimit ? { pidsLimit: s.pidsLimit } : {}),
    };
  }

  /**
   * After the run's container stopped: note services that broke during the run, stop them, then
   * keep their logs and `collect` paths in `output/services/<name>/`.
   */
  private async stopServices(id: string): Promise<void> {
    if (this.mustGet(id).services.length === 0) return;
    const base = join(this.dirs(id).output, "services");
    const failures = new Map<string, string>();
    for (const svc of this.mustGet(id).services) {
      if (!svc.containerId) continue;
      const st = await docker.inspectContainer(svc.containerId).catch(() => null);
      if (!st) failures.set(svc.name, "container disappeared");
      else if (!st.running && (st.exitCode !== 0 || st.oomKilled))
        failures.set(
          svc.name,
          `exited with code ${st.exitCode}${st.oomKilled ? " (out of memory)" : ""}`,
        );
      else if (st.health === "unhealthy") failures.set(svc.name, "unhealthy");
    }
    const run = this.mustGet(id);
    for (const svc of run.services) svc.failure = failures.get(svc.name) ?? svc.failure;
    this.save(run, "service", "stopping services");
    await Promise.all(
      run.services.map((s) => (s.containerId ? docker.stopContainer(s.containerId) : null)),
    );
    for (const svc of run.services) {
      const spec = run.spec.services.find((x) => x.name === svc.name);
      if (!svc.containerId || !spec) continue;
      const dir = join(base, svc.name);
      mkdirSync(dir, { recursive: true });
      const logs = docker.followLogs(svc.containerId, join(dir, "log"), this.redactor(run));
      await Promise.race([logs.done, sleep(LOG_DRAIN_TIMEOUT_MS)]);
      logs.proc.kill();
      const missing: string[] = [];
      for (const p of spec.collect) {
        const dest = safeJoin(dir, `.${p}`);
        const err = dest
          ? await docker.copyFromContainer(svc.containerId, p, dest)
          : "path leaves the output directory";
        if (err) missing.push(`${p} (${err})`);
      }
      const what = `${svc.name}: ${svc.failure ? `failed during the run (${svc.failure}); ` : ""}${spec.collect.length - missing.length}/${spec.collect.length} collected`;
      this.store.addEvent(
        id,
        "service",
        `${what}${missing.length ? `; missing ${missing.join("; ")}` : ""}`,
      );
    }
  }

  /** Copy `spec.collect` paths out of the stopped container into `output/collected/`. */
  private async collect(run: Run, containerId: string): Promise<void> {
    if (run.spec.collect.length === 0) return;
    const base = join(this.dirs(run.id).output, "collected");
    const missing: string[] = [];
    for (const p of run.spec.collect) {
      const dest = safeJoin(base, `.${p}`);
      const err = dest
        ? await docker.copyFromContainer(containerId, p, dest)
        : "path leaves the output directory";
      if (err) missing.push(`${p} (${err})`);
    }
    const n = run.spec.collect.length - missing.length;
    this.store.addEvent(
      run.id,
      "collect",
      `${n}/${run.spec.collect.length} collected${missing.length ? `; missing ${missing.join("; ")}` : ""}`,
    );
  }

  // ---- process backend ----

  private async launchProcess(run: Run, dirs: RunDirs, ctl: Control): Promise<void> {
    const id = run.id;
    const envFile = this.envFile(id);
    try {
      const binDir = join(dirs.root, "bin");
      const home = join(dirs.root, "home");
      mkdirSync(binDir, { recursive: true });
      mkdirSync(home, { recursive: true });
      const gpuIds = run.lease?.gpuIds ?? [];
      const cfg: ShimConfig = {
        realDocker: which("docker") ?? "docker",
        dockerConfig: dockerConfigDir(),
        runId: id,
        homeLabel: this.homeLabel,
        gpuIds,
        gpuMode: this.gpuMode,
        hostNetwork: run.spec.hostNetwork,
        auth: null,
      };
      if (run.spec.auth) {
        const h = await this.prepareAuth(run, dirs);
        if (Object.keys(h.secretEnv).length > 0)
          writeFileSync(envFile, docker.envFileText(h.secretEnv), { mode: 0o600 });
        cfg.auth = {
          mounts: h.mounts,
          agentDir: dirs.agent,
          env: h.env,
          envFile: Object.keys(h.secretEnv).length > 0 ? envFile : null,
          pathDirs: h.cli.pathDirs,
        };
      }
      writeShim(binDir, join(dirs.root, "shim.json"), this.deps.shim as string[], cfg);
      const cwd =
        run.spec.cwd ??
        (run.code ? join(dirs.workspace, run.code.subdir) : (run.spec.project ?? dirs.root));
      const env = processEnv({
        binDir,
        home,
        exitFile: join(dirs.root, "exit-code"),
        extra: {
          ...run.spec.env,
          ...this.passEnv(run),
          ORBIT_RUN_ID: id,
          ORBIT_OUTPUT: dirs.output,
          ORBIT_METRICS: dirs.metrics,
          PYTHONUNBUFFERED: "1",
          CUDA_VISIBLE_DEVICES: gpuIds.join(","),
        },
      });
      if (ctl.cancel)
        return void (await this.finalize(
          this.mustGet(id),
          "cancelled",
          null,
          "cancelled before start",
        ));
      appendFileSync(dirs.log, `[orbit] process in ${cwd}\n`);
      const child = spawnProcess({ command: run.spec.command, cwd, env, log: dirs.log });
      const exited = new Promise<number | null>((done) => {
        child.once("error", (e) => {
          appendFileSync(dirs.log, `[orbit] ${e.message}\n`);
          done(127);
        });
        child.once("exit", (code, signal) =>
          done(code ?? (signal ? 128 + signalNumber(signal) : null)),
        );
      });
      const pid = child.pid;
      const start = pid ? procStart(pid) : null;
      const fresh = this.mustGet(id);
      fresh.proc = pid && start ? { pid, start } : null;
      fresh.state = "running";
      fresh.startedAt = nowIso();
      this.save(fresh, "started", pid ? `process ${pid}` : "process failed to start");
      if (ctl.cancel) void this.stopProcess(fresh);
      this.armTimeout(fresh);
      await this.watchProcess(id, exited);
    } catch (e) {
      const msg = (e as Error).message;
      appendFileSync(dirs.log, `\n[orbit] ${this.redactor(run).apply(msg)}\n`);
      await this.finalize(this.mustGet(id), "failed", null, msg);
    } finally {
      this.active.delete(id);
    }
  }

  /** Wait for the process (via its exit event, or by polling after a restart), then finalize. */
  private async watchProcess(id: string, exited: Promise<number | null> | null): Promise<void> {
    const ctl = this.control(id);
    this.startUsage(id, async () => {
      const r = this.mustGet(id);
      const children = (await docker.containersWithLabel(docker.LABEL_PARENT, id)) ?? [];
      return {
        cgroups: await this.containerCgroups(children),
        group: r.proc ? { pgid: r.proc.pid, since: Number(r.proc.start) } : null,
        gpus: (r.lease?.gpuIds.length ?? 0) > 0,
      };
    });
    let code: number | null = null;
    if (exited) code = await exited;
    else {
      for (;;) {
        const r = this.mustGet(id);
        if (!r.proc || !procAlive(r.proc)) break;
        await sleep(PROC_POLL_MS);
      }
    }
    this.disarmTimeout(id);
    const run = this.mustGet(id);
    await this.stopUsage(run, false);
    code = readExitFile(join(this.dirs(id).root, "exit-code")) ?? code;
    const reason = code === 0 ? null : code === null ? "exit status unknown" : `exit code ${code}`;
    await this.finalize(run, ...outcome(run, ctl, code, reason));
  }

  /** The run's control entry, taking over a stop requested before it existed (e.g. at recovery). */
  private control(id: string): Control {
    const ctl = this.active.get(id) ?? {};
    ctl.cancel ??= this.stopIntent.get(id);
    this.stopIntent.delete(id);
    this.active.set(id, ctl);
    return ctl;
  }

  /** SIGTERM the process group and stop its child containers; SIGKILL after a grace period. */
  private async stopProcess(run: Run): Promise<void> {
    const proc = run.proc;
    if (proc && procAlive(proc)) {
      killGroup(proc.pid, "SIGTERM");
      setTimeout(() => {
        if (groupAlive(proc)) killGroup(proc.pid, "SIGKILL");
      }, STOP_GRACE_MS).unref();
    }
    const children = await docker.containersWithLabel(docker.LABEL_PARENT, run.id);
    await Promise.all((children ?? []).map((c) => docker.stopContainer(c)));
  }

  /** True when no process of the group and no child container is left. */
  private async cleanupProcess(run: Run): Promise<boolean> {
    const proc = run.proc;
    if (proc && groupAlive(proc)) {
      killGroup(proc.pid, "SIGKILL");
      for (let i = 0; i < 20 && groupAlive(proc); i++) await sleep(250);
    }
    rmSync(this.envFile(run.id), { force: true });
    const children = await docker.containersWithLabel(docker.LABEL_PARENT, run.id);
    if (children === null) return false;
    const removed = await Promise.all(children.map((c) => docker.removeContainer(c)));
    const ok = removed.every(Boolean) && !(proc && groupAlive(proc));
    if (ok && children.length > 0)
      this.store.addEvent(run.id, "cleanup", `removed ${children.length} child container(s)`);
    return ok;
  }

  /** Remove a run's service containers, then its networks; true once all are gone. */
  private async cleanupServices(run: Run): Promise<boolean> {
    const children = await docker.containersWithLabel(docker.LABEL_PARENT, run.id);
    if (children === null) return false;
    const removed = await Promise.all(children.map((c) => docker.removeContainer(c)));
    if (!removed.every(Boolean)) return false;
    const nets = await docker.networksWithLabel(docker.LABEL_PARENT, run.id);
    if (nets === null) return false;
    const gone = await Promise.all(nets.map((n) => docker.removeNetwork(n)));
    if (children.length + nets.length > 0)
      this.store.addEvent(
        run.id,
        "cleanup",
        `removed ${children.length} service container(s) and ${nets.length} network(s)`,
      );
    return gone.every(Boolean);
  }

  private async recoverProcess(run: Run): Promise<void> {
    if (!run.proc) {
      await this.finalize(run, "lost", null, "process never started before daemon restart");
      return;
    }
    const alive = procAlive(run.proc);
    this.save(
      run,
      "recovered",
      alive ? "reattached to process after daemon restart" : "collected after daemon restart",
    );
    this.control(run.id);
    if (alive) this.armTimeout(run);
    void this.watchProcess(run.id, null)
      .catch((e) => console.error(`orbit: run ${run.id}:`, (e as Error).message))
      .finally(() => this.active.delete(run.id));
  }

  /** Process output goes straight to the log file; redact known secrets once it is complete. */
  private async redactLog(run: Run): Promise<void> {
    const r = this.redactor(run);
    if (r.empty) return;
    const log = this.dirs(run.id).log;
    const tmp = `${log}.redact`;
    try {
      await pipeline(createReadStream(log), r.stream(), createWriteStream(tmp));
      renameSync(tmp, log);
    } catch {
      rmSync(tmp, { force: true });
    }
  }

  /** Agent CLI + credentials for `spec.auth`; the secret variables go through a private env file. */
  private async prepareAuth(run: Run, dirs: RunDirs): Promise<Prepared> {
    const name = run.spec.auth as string;
    const entry = this.deps.auth?.get(name);
    if (!entry) throw new Error(`auth profile not found: ${name}`);
    const h = await prepareHarness(entry, dirs.agent);
    if (run.spec.agentBundle) {
      installBundle(run.spec.agentBundle, dirs.agent, entry.profile.harness);
      this.store.addEvent(run.id, "bundle", `method bundle ${run.spec.agentBundle}`);
    }
    this.store.addEvent(
      run.id,
      "harness",
      `${h.cli.version} · auth ${name} (${entry.profile.kind})${run.spec.hostNetwork ? " · host network" : ""}`,
    );
    return h;
  }

  private async ensureImage(run: Run, dirs: RunDirs): Promise<string> {
    const image = run.spec.image;
    if (image) {
      // Pulled here, without the time limit of `docker run`, with progress in the run log.
      if (await docker.imageExists(image)) return image;
      this.save(run, "pull", `pulling ${image}`);
      const code = await docker.pullImage(image, dirs.log);
      if (code !== 0) throw new Error(`docker pull ${image} failed with exit code ${code}`);
      return image;
    }
    const df = this.buildFile(run, dirs);
    if (df !== run.spec.dockerfile)
      this.store.addEvent(
        run.id,
        "image",
        `building from the code snapshot (${relative(dirs.workspace, df)})`,
      );
    const dir = basename(dirname(df));
    const name = run.spec.project
      ? basename(run.spec.project)
      : GENERIC_DIRS.has(dir)
        ? `${basename(dirname(dirname(df)))}-${dir}`
        : dir;
    const tag = this.bundleTag(df, name) ?? docker.dockerfileTag(df, dirname(df), name);
    if (await docker.imageExists(tag)) {
      this.store.addEvent(run.id, "image", `reusing ${tag}`);
      return tag;
    }
    this.save(run, "build", `building ${tag}`);
    appendFileSync(dirs.log, `[orbit] docker build -f ${df} -t ${tag}\n`);
    const code = await docker.buildImage(df, dirname(df), tag, dirs.log, {
      hostNetwork: run.spec.hostNetwork,
    });
    if (code !== 0) throw new Error(`docker build failed with exit code ${code}`);
    appendFileSync(dirs.log, "[orbit] build done\n");
    return tag;
  }

  /**
   * The Dockerfile to build: a Dockerfile inside the snapshotted repository is taken from the snapshot,
   * with the snapshot as its context, so the image matches the code the run was submitted with (as
   * on a worker). Outside the repository, or not in the snapshot (gitignored), the original is used.
   */
  private buildFile(run: Run, dirs: RunDirs): string {
    const df = run.spec.dockerfile as string;
    if (!run.code) return df;
    // The repository root is a real path; the Dockerfile may have been given through a symlink.
    const rel = relative(run.code.repo, realOr(df));
    if (rel.startsWith("..") || isAbsolute(rel)) return df;
    const inSnapshot = join(dirs.workspace, rel);
    return existsSync(inSnapshot) ? inSnapshot : df;
  }

  /** A Dockerfile inside a received bundle: the bundle hash already names its whole context. */
  private bundleTag(df: string, name: string): string | null {
    const rel = df.startsWith(`${this.paths.bundles}/`)
      ? df.slice(this.paths.bundles.length + 1)
      : null;
    if (!rel) return null;
    const hash = createHash("sha256").update(rel).digest("hex").slice(0, 12);
    const repo =
      name
        .toLowerCase()
        .replace(/[^a-z0-9._-]+/g, "-")
        .replace(/^[^a-z0-9]+/, "") || "run";
    return `orbit-local/${repo}:b${hash}`;
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
    for (const m of s.mounts) {
      const source = m.source ?? this.deps.datasets?.path(m.dataset as string);
      if (!source) throw new Error(`dataset ${m.dataset} is not registered on ${this.node}`);
      mounts.push({ source, target: m.target, mode: m.mode });
    }
    const workdirOut = s.workdir === "image" ? null : (s.workdir ?? workdir);
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
      command: runCommand(s),
      labels: { [docker.LABEL_RUN]: run.id, [docker.LABEL_HOME]: this.homeLabel },
      gpuIds: run.lease?.gpuIds ?? [],
      gpuMode: this.gpuMode,
      cpus: s.resources.cpus,
      memGB: s.resources.memGB,
      mounts,
      env,
      workdir: workdirOut,
      network: !s.network ? "none" : s.hostNetwork ? "host" : "bridge",
      user,
    };
  }

  /** Follow logs and wait for exit, then collect and clean up. */
  private async watch(id: string, containerId: string, recovered: boolean): Promise<void> {
    const ctl = this.control(id);
    const dirs = this.dirs(id);
    this.startUsage(id, async () => ({
      cgroups: await this.containerCgroups([
        containerId,
        ...this.mustGet(id).services.flatMap((s) => (s.containerId ? [s.containerId] : [])),
      ]),
      group: null,
      gpus: (this.mustGet(id).lease?.gpuIds.length ?? 0) > 0,
    }));
    // The container log follows the build output and Orbit's own lines; a reattach after a restart
    // re-reads the container log from its start, so it replaces only the part after that offset.
    const offsetFile = join(dirs.root, "log-offset");
    if (!recovered) writeFileSync(offsetFile, String(fileSize(dirs.log)));
    else truncateSync(dirs.log, Math.min(readOffset(offsetFile), fileSize(dirs.log)));
    const logs = docker.followLogs(containerId, dirs.log, this.redactor(this.mustGet(id)));
    ctl.logs = logs.proc;
    const drained = logs.done.then(() => true);
    let exitCode: number;
    let collected = false;
    const spec = this.mustGet(id).spec;
    if (keepsContainer(spec)) {
      const main = await this.waitMain(id, containerId);
      exitCode = main.exitCode;
      this.disarmTimeout(id);
      if (main.running) {
        // As Harbor: hooks in the run's container first; without an after phase it is stopped
        // before the services' hooks run.
        const go = () => ctl.cancel !== "cancel";
        if (go()) await this.runHooks(id, containerId, "main");
        if (!spec.after) {
          await docker.stopContainer(containerId);
          await this.waitStopped(containerId);
        }
        if (go()) await this.runHooks(id, containerId, "services");
        // Artifacts are taken as the command left them, before the after phase can change them.
        await this.collect(this.mustGet(id), containerId);
        collected = true;
        if (spec.after) {
          await this.runAfter(id, containerId, ctl);
          await docker.stopContainer(containerId);
          await this.waitStopped(containerId);
        }
      } else if (spec.after) this.skipAfter(id, "the container stopped with the command");
    } else exitCode = await this.waitStopped(containerId);
    this.disarmTimeout(id);
    // Evidence first: let the log follower reach EOF before the container is removed.
    const complete = await Promise.race([drained, sleep(LOG_DRAIN_TIMEOUT_MS).then(() => false)]);
    if (!complete) {
      logs.proc.kill();
      appendFileSync(dirs.log, "\n[orbit] log collection timed out; log may be truncated\n");
      this.store.addEvent(id, "log", "log collection timed out; log may be truncated");
    }
    // The after phase wrote its output to a file; it follows the container log, not inside it.
    const afterLog = join(dirs.orbit, "phases", "after.log");
    if (this.mustGet(id).spec.after && existsSync(afterLog)) {
      appendFileSync(dirs.log, "\n[orbit] after phase output:\n");
      appendFileSync(
        dirs.log,
        this.redactor(this.mustGet(id)).apply(readFileSync(afterLog, "utf8")),
      );
    }
    const st = await docker.inspectContainer(containerId).catch(() => null);
    let run = this.mustGet(id);
    if (!collected) await this.collect(run, containerId);
    await this.stopServices(id);
    run = this.mustGet(id);
    // Docker flags any OOM kill in the container; only a failed exit means the run itself died of it.
    const oom = Boolean(st?.oomKilled) && exitCode !== 0;
    await this.stopUsage(run, oom);
    let reason = exitCode === 0 ? null : `exit code ${exitCode}`;
    if (oom) reason = `out of memory (limit ${run.spec.resources.memGB} GB)`;
    await this.finalize(run, ...outcome(run, ctl, exitCode, reason));
  }

  /** Exit code once the container has stopped (`docker wait`, retried while docker is unavailable). */
  private async waitStopped(containerId: string): Promise<number> {
    let exitCode = await docker.waitContainer(containerId);
    // `docker wait` also fails when docker itself is unavailable: only a stopped container counts.
    while (exitCode === -1) {
      const st = await docker.inspectContainer(containerId).catch(() => undefined);
      if (st === null) break;
      if (st && !st.running) {
        exitCode = st.exitCode;
        break;
      }
      await sleep(DOCKER_RETRY_MS);
      exitCode = await docker.waitContainer(containerId);
    }
    return exitCode;
  }

  /**
   * A run with an after phase: wait for the command's exit code (written by the phase script), or
   * for the container to stop first (killed, out of memory, cancelled).
   */
  private async waitMain(
    id: string,
    containerId: string,
  ): Promise<{ exitCode: number; running: boolean }> {
    const file = join(this.dirs(id).orbit, "phases", "main.exit");
    for (let i = 0; ; i++) {
      const code = readCode(file);
      if (code !== null) return { exitCode: code, running: true };
      if (i % 5 === 0) {
        const st = await docker.inspectContainer(containerId).catch(() => undefined);
        if (st === null) return { exitCode: -1, running: false };
        if (st && !st.running) {
          // The command may have finished just before the container stopped.
          const late = readCode(file);
          return { exitCode: late ?? st.exitCode, running: false };
        }
      }
      await sleep(1000);
    }
  }

  /** Stop the command of a run with an after phase (its whole session), keeping the container. */
  private async stopMain(containerId: string): Promise<void> {
    const kill = (sig: string) =>
      docker.execWait(containerId, [
        "sh",
        "-c",
        `p=$(cat /orbit/phases/main.pid 2>/dev/null) && { kill -${sig} -"$p" 2>/dev/null || kill -${sig} "$p"; }`,
      ]);
    await kill("TERM");
    await sleep(10_000);
    await kill("KILL");
  }

  /** `spec.hooks`, in order, each in its container with its time limit; failures are noted only. */
  private async runHooks(id: string, containerId: string, which: "main" | "services") {
    const run = this.mustGet(id);
    for (const [i, h] of run.spec.hooks.entries()) {
      if (Boolean(h.service) !== (which === "services")) continue;
      const target = h.service
        ? run.services.find((s) => s.name === h.service)?.containerId
        : containerId;
      const where = h.service ?? "main";
      if (!target) {
        this.store.addEvent(id, "hook", `hook ${i + 1} (${where}): service not running`);
        continue;
      }
      const code = await docker.execWait(target, ["sh", "-c", h.command], h.timeoutSec * 1000);
      this.store.addEvent(
        id,
        "hook",
        `hook ${i + 1} (${where}): ${code === 0 ? "done" : code === 124 ? `exit 124 (or no exit within ${h.timeoutSec} s)` : `exit code ${code}`}`,
      );
    }
  }

  private setAfter(id: string, status: AfterStatus, message: string): void {
    const run = this.mustGet(id);
    run.after = status;
    this.save(run, "after", message);
  }

  private skipAfter(id: string, why: string): void {
    const now = nowIso();
    this.setAfter(
      id,
      { state: "skipped", exitCode: null, reason: why, startedAt: null, endedAt: now },
      `after phase skipped: ${why}`,
    );
  }

  /**
   * The after phase: copy its files in, switch the network if asked, run it detached (it writes
   * its output and exit code under /orbit/phases, so it survives a daemon restart), wait up to its
   * timeout, then keep its `collect` paths in `output/after/` (its output joins the run log later).
   */
  private async runAfter(id: string, containerId: string, ctl: Control): Promise<void> {
    const dirs = this.dirs(id);
    const phases = join(dirs.orbit, "phases");
    const run = this.mustGet(id);
    const a = run.spec.after as AfterPhase;
    // Read afresh each time: a cancel can arrive while the phase runs.
    const cancelled = () => ctl.cancel === "cancel";
    if (cancelled() || ctl.fail) return this.skipAfter(id, ctl.fail ?? "run cancelled");
    const fail = (why: string) =>
      this.setAfter(
        id,
        { state: "error", exitCode: null, reason: why, startedAt: null, endedAt: nowIso() },
        `after phase not started: ${why}`,
      );
    let startedAt = run.after?.state === "running" ? run.after.startedAt : null;
    if (!startedAt) {
      for (const c of a.copy) {
        const err = await docker.copyToContainer(containerId, c.source, c.target);
        if (err) return fail(`copy to ${c.target}: ${err}`);
      }
      if (a.network !== undefined && a.network !== run.spec.network) {
        const nets = (await docker.containerNetworks(containerId)) ?? [];
        if (a.network) {
          if (!(await docker.connectNetwork("bridge", containerId)))
            return fail("cannot connect the container to a network");
        } else
          for (const n of nets)
            if (!(await docker.disconnectNetwork(n, containerId)))
              return fail(`cannot disconnect network ${n}`);
      }
      const secrets: Record<string, string> = {};
      for (const k of a.passEnv) if (process.env[k] !== undefined) secrets[k] = process.env[k];
      const envFile = join(this.paths.tmp, `${id}.after.env`);
      if (Object.keys(secrets).length)
        writeFileSync(envFile, docker.envFileText(secrets), { mode: 0o600 });
      startedAt = nowIso();
      this.setAfter(
        id,
        { state: "running", exitCode: null, reason: null, startedAt, endedAt: null },
        "after phase started",
      );
      const err = await docker
        .execDetached(
          containerId,
          [
            "sh",
            "-c",
            '"$@" > /orbit/phases/after.log 2>&1; echo $? > /orbit/phases/after.exit',
            "sh",
            ...a.command,
          ],
          a.env,
          Object.keys(secrets).length ? envFile : undefined,
        )
        .finally(() => rmSync(envFile, { force: true }));
      if (err) return fail(`docker exec: ${err}`);
    }
    const deadline = Date.parse(startedAt) + a.timeoutMin * 60_000;
    let code: number | null = null;
    for (;;) {
      code = readCode(join(phases, "after.exit"));
      if (code !== null || Date.now() >= deadline) break;
      const st = await docker.inspectContainer(containerId).catch(() => undefined);
      if (st === null || (st && !st.running)) break;
      if (this.mustGet(id).state !== "running" || cancelled()) break;
      await sleep(1000);
    }
    const base = join(dirs.output, "after");
    const missing: string[] = [];
    for (const p of a.collect) {
      const dest = safeJoin(base, `.${p}`);
      const e = dest ? await docker.copyFromContainer(containerId, p, dest) : "leaves the output";
      if (e) missing.push(`${p} (${e})`);
    }
    if (a.collect.length)
      this.store.addEvent(
        id,
        "collect",
        `after: ${a.collect.length - missing.length}/${a.collect.length} collected${missing.length ? `; missing ${missing.join("; ")}` : ""}`,
      );
    const endedAt = nowIso();
    const status: AfterStatus =
      code !== null
        ? {
            state: code === 0 ? "succeeded" : "failed",
            exitCode: code,
            reason: code === 0 ? null : `exit code ${code}`,
            startedAt,
            endedAt,
          }
        : Date.now() >= deadline
          ? {
              state: "timeout",
              exitCode: null,
              reason: `timeout after ${a.timeoutMin} min`,
              startedAt,
              endedAt,
            }
          : {
              state: "error",
              exitCode: null,
              reason: cancelled() ? "run cancelled" : "the container stopped",
              startedAt,
              endedAt,
            };
    this.setAfter(
      id,
      status,
      `after phase ${status.state}${status.reason ? `: ${status.reason}` : ""}`,
    );
  }

  private requestStop(run: Run, why: "cancel" | "timeout"): void {
    const ctl = this.active.get(run.id);
    if (ctl) ctl.cancel ??= why;
    // Not watched yet (the daemon is still reattaching): the watcher takes it over.
    else this.stopIntent.set(run.id, why);
    this.store.addEvent(run.id, why, why === "cancel" ? "cancel requested" : "timeout reached");
    // At its timeout, a run with an after phase stops only the command; the phase still runs.
    if (run.containerId && why === "timeout" && keepsContainer(run.spec))
      void this.stopMain(run.containerId);
    else if (run.containerId) void docker.stopContainer(run.containerId);
    if (run.proc) void this.stopProcess(run);
  }

  /** Terminal transition: record the outcome, remove the container, release the lease. */
  private async finalize(
    run: Run,
    state: RunState,
    exitCode: number | null,
    reason: string | null,
  ): Promise<Run> {
    this.disarmTimeout(run.id);
    // Already ended (e.g. a later step of the same watcher threw): only retry its cleanup.
    const now = this.mustGet(run.id);
    if (isTerminal(now.state)) {
      if (now.cleanup !== "done") await this.cleanup(now);
      return this.mustGet(run.id);
    }
    run.state = state;
    run.exitCode = exitCode;
    run.reason = reason === null ? null : this.redactor(run).apply(reason);
    run.endedAt = nowIso();
    if (run.spec.auth) this.finishAuth(run);
    if (run.spec.backend === "process") await this.redactLog(run);
    this.save(run, state, run.reason ?? (exitCode !== null ? `exit code ${exitCode}` : state));
    await this.cleanup(run);
    void this.tick();
    return this.mustGet(run.id);
  }

  /** Remove credential files from the Agent home; keep a refreshed Codex login. */
  private finishAuth(run: Run): void {
    const name = run.spec.auth as string;
    const entry = this.deps.auth?.get(name) ?? null;
    const { refreshed } = finishHarness(entry, this.dirs(run.id).agent);
    if (refreshed) {
      this.deps.auth?.updateSecret(name, refreshed);
      this.store.addEvent(run.id, "auth", `refreshed login saved to profile ${name}`);
    }
  }

  /**
   * Redacts every stored secret, plus the run's secret-looking `passEnv` values; rebuilt per use so
   * new or changed profiles are covered.
   */
  redactor(run?: Run): Redactor {
    const extra = run
      ? [...run.spec.passEnv, ...(run.spec.after?.passEnv ?? [])]
          .filter((k) => SECRET_NAME.test(k))
          .map((k) => process.env[k] ?? "")
          .filter((v) => v.length >= 8)
      : [];
    return new Redactor([...(this.deps.auth?.allSecrets() ?? []), ...extra]);
  }

  private async cleanup(run: Run): Promise<void> {
    // By name as well: `docker run` can create the container and still fail before returning its id.
    const removed =
      run.spec.backend === "process"
        ? await this.cleanupProcess(run)
        : (await docker.removeContainer(run.containerId ?? containerName(run.id))) &&
          (!usesRunNetworks(run.spec) || (await this.cleanupServices(run)));
    const fresh = this.mustGet(run.id);
    if (!removed) {
      if (fresh.cleanup !== "failed") {
        fresh.cleanup = "failed";
        this.save(
          fresh,
          "cleanup",
          run.spec.backend === "process"
            ? "process or child containers still present; lease kept until they are gone"
            : "container removal failed; lease kept until it succeeds",
        );
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
      const what =
        run.spec.backend === "process" ? "process and child containers gone" : "container removed";
      this.save(fresh, "cleanup", lease ? `${what}, lease released` : "done");
    });
    void this.measure(fresh.id);
  }

  /** Record the size of a finished run's directory (outputs no longer change once cleaned up). */
  private async measure(id: string): Promise<void> {
    const bytes = await dirBytes(this.dirs(id).root);
    const run = this.store.getRun(id);
    if (bytes === null || !run || run.sizeBytes === bytes) return;
    run.sizeBytes = bytes;
    this.save(run);
  }

  /** Measure finished runs recorded before sizes were (one at a time, in the background). */
  private async measureMissing(): Promise<void> {
    for (const r of this.store.unmeasuredRuns()) {
      if (this.stopped) return;
      await this.measure(r.id);
    }
  }

  private async retryCleanup(): Promise<void> {
    for (const run of this.store.pendingCleanup()) {
      if (run.remote) continue;
      if (!this.active.has(run.id)) await this.cleanup(run);
    }
  }

  /** Reattach to runs that were active when the daemon last stopped. */
  private async recover(first = true): Promise<void> {
    for (const run of this.store.listRuns({ states: ["starting", "running"], limit: 10_000 })) {
      if (this.active.has(run.id)) continue;
      if (run.remote) {
        if (!first) continue;
        // Mirrored from a worker; the cluster sync resumes it (or re-sends it if never confirmed).
        const sync = this.store.getSync(run.id);
        if (sync && !sync.confirmed) void this.dispatchRemote(run.id);
        continue;
      }
      if (run.spec.backend === "process") {
        await this.recoverProcess(run);
        continue;
      }
      let st: docker.ContainerStatus | null;
      try {
        st = await docker.inspectContainer(run.containerId ?? containerName(run.id));
      } catch (e) {
        // Docker is not answering: never conclude the run is lost from that; try again later.
        console.error(`orbit: recover ${run.id}:`, (e as Error).message);
        setTimeout(() => void this.recover(false), DOCKER_RETRY_MS * 6).unref();
        return;
      }
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
      this.control(run.id);
      if (st.running) this.armTimeout(run);
      const id = st.id;
      void this.watch(run.id, id, true)
        .catch((e) => console.error(`orbit: run ${run.id}:`, (e as Error).message))
        .finally(() => this.active.delete(run.id));
    }
  }

  // ---- resource use ----

  /** cgroup directories of containers by id, cached (a container keeps its cgroup). */
  private readonly cgroupDirs = new Map<string, string>();

  private async containerCgroups(ids: string[]): Promise<string[]> {
    const out: string[] = [];
    for (const c of ids) {
      let dir = this.cgroupDirs.get(c);
      if (!dir) {
        const st = await docker.inspectContainer(c).catch(() => null);
        const found = st?.pid ? cgroupOf(st.pid) : null;
        if (!found) continue;
        dir = found;
        this.cgroupDirs.set(c, dir);
      }
      out.push(dir);
    }
    return out;
  }

  /** Sample a run's resource use while it runs; samples are saved without a change event. */
  private startUsage(id: string, targets: () => Promise<Targets>): void {
    if (this.samplers.has(id)) return;
    const prev = this.store.getRun(id)?.usage ?? null;
    const sampler = new UsageSampler(
      prev,
      targets,
      (usage) => {
        const r = this.store.getRun(id);
        if (!r || isTerminal(r.state)) return;
        r.usage = { ...usage };
        this.store.putRun(r);
      },
      this.deps.usageMs ?? 5000,
    );
    this.samplers.set(id, sampler);
  }

  /** Stop sampling and put the final figures on `run` (saved with its terminal state). */
  private async stopUsage(run: Run, oomKilled: boolean): Promise<void> {
    const sampler = this.samplers.get(run.id);
    this.samplers.delete(run.id);
    if (!sampler) return;
    const usage = await sampler.stop();
    // Too short to be seen (or nothing readable): no figures rather than zeros.
    if (sampler.meter.readings === 0 && !run.usage && !oomKilled) return;
    run.usage = { ...usage, oomKilled };
    if (oomKilled) run.usage.oomKills = Math.max(1, run.usage.oomKills);
    const u = run.usage;
    this.store.addEvent(
      run.id,
      "usage",
      `peak memory ${u.peakMemGB} GB of ${run.spec.resources.memGB} GB` +
        `, CPU peak ${u.peakCpus} / mean ${u.meanCpus} of ${run.spec.resources.cpus}` +
        (u.peakGpuMemGB !== null ? `, GPU memory peak ${u.peakGpuMemGB} GB` : "") +
        (u.oomKills ? `, ${u.oomKills} process(es) killed for memory` : ""),
    );
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
    this.changed(run, event);
  }

  private changed(run: Run, event?: RunEvent): void {
    const change = { run: structuredClone(run), event };
    this.store.afterCommit(() => this.emit("change", change));
  }
}

const containerName = (runId: string) => `orbit-${runId}`;

/**
 * The container command: `mkdirs` first (best effort), and with an after phase the phase script,
 * which keeps the container once the command has exited.
 */
function runCommand(s: RunSpec): string[] {
  let cmd = keepsContainer(s) ? ["/bin/sh", "/orbit/phases/run.sh", ...s.command] : s.command;
  if (s.mkdirs.length)
    cmd = [
      "/bin/sh",
      "-c",
      `mkdir -p ${docker.shellJoin(s.mkdirs)} 2>/dev/null; exec "$@"`,
      "sh",
      ...cmd,
    ];
  return cmd;
}

/** Runs whose container stays once the command exits: for hooks and an after phase. */
const keepsContainer = (s: RunSpec) => Boolean(s.after) || s.hooks.length > 0;

/** Per-run networks: for services, or for an after phase that has network when the run has none. */
const usesRunNetworks = (s: RunSpec) =>
  s.services.length > 0 || (s.after?.network === true && !s.network);

/**
 * PID 1's child in a run with an after phase: start the command in its own session (so a timeout
 * can stop all of it), record its exit code, then keep the container for the after phase.
 */
const PHASE_SCRIPT = `#!/bin/sh
d=/orbit/phases
if command -v setsid >/dev/null 2>&1; then setsid "$@" & else "$@" & fi
pid=$!
echo "$pid" > "$d/main.pid"
wait "$pid"
code=$?
echo "$code" > "$d/main.exit"
while :; do sleep 3600; done
`;

function writePhaseScript(dir: string): void {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "run.sh"), PHASE_SCRIPT, { mode: 0o755 });
}

/** A small integer file the phase scripts write, or null while it does not exist (yet). */
function readCode(file: string): number | null {
  try {
    const n = Number.parseInt(readFileSync(file, "utf8").trim(), 10);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

const realOr = (p: string) => {
  try {
    return realpathSync(p);
  } catch {
    return p;
  }
};

function which(cmd: string): string | null {
  for (const d of (process.env.PATH ?? "").split(delimiter)) {
    if (d && existsSync(join(d, cmd))) return join(d, cmd);
  }
  return null;
}

function signalNumber(signal: NodeJS.Signals): number {
  return (
    ({ SIGHUP: 1, SIGINT: 2, SIGKILL: 9, SIGTERM: 15 } as Record<string, number>)[signal] ?? 15
  );
}

/**
 * Copy a method bundle into the Agent home. AGENTS.md and CLAUDE.md stand in for each other, so one
 * bundle serves both harnesses.
 */
export function installBundle(bundle: string, agentDir: string, harness: "codex" | "claude-code") {
  const home = join(agentDir, harness === "codex" ? "codex" : "claude");
  mkdirSync(home, { recursive: true });
  cpSync(bundle, home, { recursive: true, dereference: true });
  const want = harness === "codex" ? "AGENTS.md" : "CLAUDE.md";
  const other = harness === "codex" ? "CLAUDE.md" : "AGENTS.md";
  if (!existsSync(join(home, want)) && existsSync(join(home, other)))
    cpSync(join(home, other), join(home, want));
}

interface Control {
  timeout?: NodeJS.Timeout;
  cancel?: "cancel" | "timeout";
  /** A failure found by Orbit while the container runs (it is stopped, then collected). */
  fail?: string;
  logs?: { kill(): unknown };
}

export class UserError extends Error {}
export class NotFoundError extends Error {}

/** Final state and reason from the exit code and what Orbit requested. */
function outcome(
  run: Run,
  ctl: Control,
  code: number | null,
  reason: string | null,
): [RunState, number | null, string | null] {
  if (ctl.fail) return ["failed", code, ctl.fail];
  if (ctl.cancel === "cancel") return ["cancelled", code, "cancelled"];
  if (ctl.cancel === "timeout") return ["failed", code, `timeout after ${run.spec.timeoutMin} min`];
  return [code === 0 ? "succeeded" : "failed", code, reason];
}

const fileSize = (f: string) => (existsSync(f) ? statSync(f).size : 0);

function readOffset(f: string): number {
  try {
    const n = Number.parseInt(readFileSync(f, "utf8"), 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
