import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { AfterPhase, AfterStatus, RunSpec } from "../contracts/index.ts";
import * as docker from "../executor/docker.ts";
import { nowIso } from "../lib/ids.ts";
import { safeJoin } from "../records/index.ts";
import type { RunContext } from "./context.ts";
import { type Control, sleep } from "./execution.ts";

type Context = Pick<
  RunContext,
  "dirs" | "mustGet" | "paths" | "save" | "setAfter" | "skipAfter" | "store"
>;

export async function waitMain(
  ctx: Context,
  id: string,
  containerId: string,
): Promise<{ exitCode: number; running: boolean }> {
  const file = join(ctx.dirs(id).orbit, "phases", "main.exit");
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

export async function stopMain(_ctx: Context, containerId: string): Promise<void> {
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

export async function runHooks(
  ctx: Context,
  id: string,
  containerId: string,
  which: "main" | "services",
) {
  const run = ctx.mustGet(id);
  for (const [i, h] of run.spec.hooks.entries()) {
    if (Boolean(h.service) !== (which === "services")) continue;
    const target = h.service
      ? run.services.find((s) => s.name === h.service)?.containerId
      : containerId;
    const where = h.service ?? "main";
    if (!target) {
      ctx.store.addEvent(id, "hook", `hook ${i + 1} (${where}): service not running`);
      continue;
    }
    const code = await docker.execWait(target, ["sh", "-c", h.command], h.timeoutSec * 1000);
    ctx.store.addEvent(
      id,
      "hook",
      `hook ${i + 1} (${where}): ${code === 0 ? "done" : code === 124 ? `exit 124 (or no exit within ${h.timeoutSec} s)` : `exit code ${code}`}`,
    );
  }
}

export function setAfter(ctx: Context, id: string, status: AfterStatus, message: string): void {
  const run = ctx.mustGet(id);
  run.after = status;
  ctx.save(run, "after", message);
}

export function skipAfter(ctx: Context, id: string, why: string): void {
  const now = nowIso();
  ctx.setAfter(
    id,
    { state: "skipped", exitCode: null, reason: why, startedAt: null, endedAt: now },
    `after phase skipped: ${why}`,
  );
}

export async function runAfter(
  ctx: Context,
  id: string,
  containerId: string,
  ctl: Control,
): Promise<void> {
  const dirs = ctx.dirs(id);
  const phases = join(dirs.orbit, "phases");
  const run = ctx.mustGet(id);
  const a = run.spec.after as AfterPhase;
  // Read afresh each time: a cancel can arrive while the phase runs.
  const cancelled = () => ctl.cancel === "cancel";
  if (cancelled() || ctl.fail) return ctx.skipAfter(id, ctl.fail ?? "run cancelled");
  const fail = (why: string) =>
    ctx.setAfter(
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
    const envFile = join(ctx.paths.tmp, `${id}.after.env`);
    if (Object.keys(secrets).length)
      writeFileSync(envFile, docker.envFileText(secrets), { mode: 0o600 });
    startedAt = nowIso();
    ctx.setAfter(
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
    if (ctx.mustGet(id).state !== "running" || cancelled()) break;
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
    ctx.store.addEvent(
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
  ctx.setAfter(
    id,
    status,
    `after phase ${status.state}${status.reason ? `: ${status.reason}` : ""}`,
  );
}

/**
 * The container command: `mkdirs` first (best effort), and with an after phase the phase script,
 * which keeps the container once the command has exited.
 */
export function runCommand(s: RunSpec): string[] {
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
export const keepsContainer = (s: RunSpec) => Boolean(s.after) || s.hooks.length > 0;

/**
 * PID 1's child in a run with an after phase: start the command in its own session (so a timeout
 * can stop all of it), record its exit code, then keep the container for the after phase.
 */
export const PHASE_SCRIPT = `#!/bin/sh
d=/orbit/phases
if command -v setsid >/dev/null 2>&1; then setsid "$@" & else "$@" & fi
pid=$!
echo "$pid" > "$d/main.pid"
wait "$pid"
code=$?
echo "$code" > "$d/main.exit"
while :; do sleep 3600; done
`;

export function writePhaseScript(dir: string): void {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "run.sh"), PHASE_SCRIPT, { mode: 0o755 });
}

/** A small integer file the phase scripts write, or null while it does not exist (yet). */
export function readCode(file: string): number | null {
  try {
    const n = Number.parseInt(readFileSync(file, "utf8").trim(), 10);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}
