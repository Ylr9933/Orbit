import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import {
  appendFileSync,
  cpSync,
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { hostname, userInfo } from "node:os";
import { basename, delimiter, dirname, isAbsolute, join, resolve } from "node:path";
import { pipeline } from "node:stream/promises";
import type { AuthStore } from "../auth/index.ts";
import { type OrbitPaths, type RunDirs, runDirs } from "../config/paths.ts";
import {
  type AuthTestResult,
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
import {
  containerPath,
  finishHarness,
  hostCli,
  type Prepared,
  prepareHarness,
} from "../harness/index.ts";
import { newId, nowIso } from "../lib/ids.ts";
import { Redactor } from "../lib/redact.ts";
import { allocate, infeasible } from "../resources/allocate.ts";
import { resolveAgentRef } from "../sessions/index.ts";
import type { RunFilter, Store } from "../store/index.ts";
import { snapshotProject } from "../workspace/snapshot.ts";
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

export interface RunServiceDeps {
  store: Store;
  paths: OrbitPaths;
  probe: () => Promise<NodeResources>;
  /** Credential profiles for `spec.auth`; runs with auth are rejected without it. */
  auth?: AuthStore;
  /** Scheduler period; the loop also runs after every submit/finish. */
  tickMs?: number;
  /**
   * Command prefix that runs this orbit binary (`node [execArgv] <entry>`); process runs get a
   * `docker` shim calling `<prefix> __docker-shim`. Without it process runs are rejected.
   */
  shim?: string[];
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
/** Directory names too generic to name an image after (the task directory is used instead). */
const GENERIC_DIRS = new Set(["environment", "tests", "docker", "env", "verifier", "solution"]);

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
  private readonly active = new Map<string, Control>();

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
    if (spec.backend === "process") {
      if (!this.deps.shim) throw new UserError("process runs are not available in this daemon");
      if (spec.cwd && (!isAbsolute(spec.cwd) || !existsSync(spec.cwd)))
        throw new UserError(`cwd not found: ${spec.cwd}`);
      if (spec.mounts.length > 0 || spec.collect.length > 0 || spec.workdir)
        throw new UserError("mounts, collect and workdir apply to docker runs only");
    }
    if (spec.agentBundle) {
      if (!spec.auth) throw new UserError("agentBundle needs an auth profile");
      if (
        !isAbsolute(spec.agentBundle) ||
        !statSync(spec.agentBundle, { throwIfNoEntry: false })?.isDirectory()
      )
        throw new UserError(`agentBundle directory not found: ${spec.agentBundle}`);
    }
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
    if (spec.auth) {
      const entry = this.deps.auth?.get(spec.auth);
      if (!entry) throw new UserError(`auth profile not found: ${spec.auth}`);
      if (entry.profile.hostNetwork) spec.hostNetwork = true;
      if (!(await hostCli(entry.profile.harness)))
        throw new UserError(`${entry.profile.harness} CLI not found on this node`);
    }
    if (spec.hostNetwork && !spec.network)
      throw new UserError("host network conflicts with network disabled");

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
      resources: { gpus: 0, cpus: 1, memGB: 2 },
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
    const ctl: Control = {};
    this.active.set(id, ctl);
    let run = this.mustGet(id);
    const dirs = this.dirs(id);
    const envFile = this.envFile(id);
    if (run.spec.backend === "process") return this.launchProcess(run, dirs, ctl);
    try {
      const image = await this.ensureImage(run, dirs);
      run = this.mustGet(id);
      run.image = image;
      if (ctl.cancel)
        return void (await this.finalize(run, "cancelled", null, "cancelled before start"));

      const spec = this.containerSpec(run, dirs, image);
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
      this.armTimeout(run);
      await this.watch(id, containerId, true);
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
    if (!run.spec.timeoutMin) return;
    const started = run.startedAt ? Date.parse(run.startedAt) : Date.now();
    const left = Math.max(0, started + run.spec.timeoutMin * 60_000 - Date.now());
    const t = setTimeout(() => {
      const now = this.store.getRun(run.id);
      if (now && !isTerminal(now.state)) this.requestStop(now, "timeout");
    }, left);
    t.unref();
  }

  /** Copy `spec.collect` paths out of the stopped container into `output/collected/`. */
  private async collect(run: Run, containerId: string): Promise<void> {
    if (run.spec.collect.length === 0) return;
    const base = join(this.dirs(run.id).output, "collected");
    const missing: string[] = [];
    for (const p of run.spec.collect) {
      const err = await docker.copyFromContainer(containerId, p, join(base, p));
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
    const ctl = this.active.get(id) ?? {};
    this.active.set(id, ctl);
    let code: number | null = null;
    if (exited) code = await exited;
    else {
      for (;;) {
        const r = this.mustGet(id);
        if (!r.proc || !procAlive(r.proc)) break;
        await sleep(PROC_POLL_MS);
      }
    }
    const run = this.mustGet(id);
    code = readExitFile(join(this.dirs(id).root, "exit-code")) ?? code;
    let state: RunState = code === 0 ? "succeeded" : "failed";
    let reason = code === 0 ? null : code === null ? "exit status unknown" : `exit code ${code}`;
    if (ctl.cancel === "cancel") {
      state = "cancelled";
      reason = "cancelled";
    } else if (ctl.cancel === "timeout") {
      state = "failed";
      reason = `timeout after ${run.spec.timeoutMin} min`;
    }
    await this.finalize(run, state, code, reason);
  }

  /** SIGTERM the process group and stop its child containers; SIGKILL after a grace period. */
  private async stopProcess(run: Run): Promise<void> {
    const proc = run.proc;
    if (proc && procAlive(proc)) {
      killGroup(proc.pid, "SIGTERM");
      setTimeout(() => {
        if (groupAlive(proc.pid)) killGroup(proc.pid, "SIGKILL");
      }, STOP_GRACE_MS).unref();
    }
    const children = await docker.containersWithLabel(docker.LABEL_PARENT, run.id);
    await Promise.all((children ?? []).map((c) => docker.stopContainer(c)));
  }

  /** True when no process of the group and no child container is left. */
  private async cleanupProcess(run: Run): Promise<boolean> {
    if (run.proc && groupAlive(run.proc.pid)) {
      killGroup(run.proc.pid, "SIGKILL");
      for (let i = 0; i < 20 && groupAlive(run.proc.pid); i++) await sleep(250);
    }
    rmSync(this.envFile(run.id), { force: true });
    const children = await docker.containersWithLabel(docker.LABEL_PARENT, run.id);
    if (children === null) return false;
    const removed = await Promise.all(children.map((c) => docker.removeContainer(c)));
    if (children.length > 0)
      this.store.addEvent(run.id, "cleanup", `removed ${children.length} child container(s)`);
    return removed.every(Boolean) && !(run.proc && groupAlive(run.proc.pid));
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
    this.active.set(run.id, {});
    this.armTimeout(run);
    void this.watchProcess(run.id, null).finally(() => this.active.delete(run.id));
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
    if (run.spec.image) return run.spec.image;
    const df = run.spec.dockerfile as string;
    const dir = basename(dirname(df));
    const name = run.spec.project
      ? basename(run.spec.project)
      : GENERIC_DIRS.has(dir)
        ? `${basename(dirname(dirname(df)))}-${dir}`
        : dir;
    const tag = docker.dockerfileTag(df, dirname(df), name);
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
      command: s.command,
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
  private async watch(id: string, containerId: string, append: boolean): Promise<void> {
    const ctl = this.active.get(id) ?? {};
    this.active.set(id, ctl);
    const dirs = this.dirs(id);
    const logs = docker.followLogs(containerId, dirs.log, append, this.redactor(this.mustGet(id)));
    ctl.logs = logs.proc;
    const drained = logs.done.then(() => true);
    const exitCode = await docker.waitContainer(containerId);
    // Evidence first: let the log follower reach EOF before the container is removed.
    const complete = await Promise.race([drained, sleep(LOG_DRAIN_TIMEOUT_MS).then(() => false)]);
    if (!complete) {
      logs.proc.kill();
      appendFileSync(dirs.log, "\n[orbit] log collection timed out; log may be truncated\n");
      this.store.addEvent(id, "log", "log collection timed out; log may be truncated");
    }
    const st = await docker.inspectContainer(containerId);
    const run = this.mustGet(id);
    await this.collect(run, containerId);
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
    if (run.proc) void this.stopProcess(run);
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
    run.reason = reason === null ? null : this.redactor().apply(reason);
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
      ? run.spec.passEnv
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
        : await docker.removeContainer(run.containerId ?? containerName(run.id));
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
  }

  private async retryCleanup(): Promise<void> {
    for (const run of this.store.pendingCleanup()) {
      if (!this.active.has(run.id)) await this.cleanup(run);
    }
  }

  /** Reattach to runs that were active when the daemon last stopped. */
  private async recover(): Promise<void> {
    for (const run of this.store.listRuns({ states: ["starting", "running"], limit: 10_000 })) {
      if (run.spec.backend === "process") {
        await this.recoverProcess(run);
        continue;
      }
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
      this.armTimeout(run);
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
  cancel?: "cancel" | "timeout";
  logs?: { kill(): unknown };
}

export class UserError extends Error {}
export class NotFoundError extends Error {}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
