// Host-process backend helpers: a detached process group writing straight to the run log, tracked
// by pid + start time so a restarted daemon can tell whether it is still the same process.
import { type ChildProcess, spawn } from "node:child_process";
import { chmodSync, closeSync, openSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { join } from "node:path";
import type { ShimConfig } from "./shim.ts";

/** Records the command's exit status in `$ORBIT_EXIT_FILE`, so it survives a daemon restart. */
const WRAPPER = '"$@"; c=$?; echo "$c" > "$ORBIT_EXIT_FILE"; exit "$c"';

const PASS_THROUGH = [
  "LANG",
  "LC_ALL",
  "TZ",
  "http_proxy",
  "https_proxy",
  "no_proxy",
  "all_proxy",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "NO_PROXY",
  "ALL_PROXY",
];

/** Names whose values are treated as secrets when passed with `passEnv`. */
export const SECRET_NAME = /KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL/i;

export interface ProcessLaunch {
  command: string[];
  cwd: string;
  env: Record<string, string>;
  log: string;
}

/** Minimal environment: nothing from the daemon except PATH, locale and proxies. */
export function processEnv(opts: {
  binDir: string;
  home: string;
  exitFile: string;
  extra: Record<string, string>;
  base?: NodeJS.ProcessEnv;
}): Record<string, string> {
  const base = opts.base ?? process.env;
  const u = userInfo();
  const env: Record<string, string> = {
    PATH: `${opts.binDir}:${base.PATH || "/usr/local/bin:/usr/bin:/bin"}`,
    HOME: opts.home,
    USER: u.username,
    LOGNAME: u.username,
  };
  for (const k of PASS_THROUGH) if (base[k]) env[k] = base[k] as string;
  env.LANG ??= "C.UTF-8";
  Object.assign(env, opts.extra);
  env.ORBIT_EXIT_FILE = opts.exitFile;
  return env;
}

export function spawnProcess(l: ProcessLaunch): ChildProcess {
  const fd = openSync(l.log, "a");
  try {
    const child = spawn("/bin/sh", ["-c", WRAPPER, "sh", ...l.command], {
      cwd: l.cwd,
      env: l.env,
      detached: true,
      stdio: ["ignore", fd, fd],
    });
    child.unref();
    return child;
  } finally {
    closeSync(fd);
  }
}

/** Start time of a process in clock ticks since boot (`/proc/<pid>/stat` field 22), or null. */
export function procStart(pid: number): string | null {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
    const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
    return fields[19] ?? null;
  } catch {
    return null;
  }
}

export function procAlive(p: { pid: number; start: string }): boolean {
  const start = procStart(p.pid);
  if (start !== p.start) return false;
  try {
    const state = readFileSync(`/proc/${p.pid}/stat`, "utf8");
    return state.slice(state.lastIndexOf(")") + 2, state.lastIndexOf(")") + 3) !== "Z";
  } catch {
    return false;
  }
}

/** Signal the whole process group; ignores groups that are already gone. */
export function killGroup(pid: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-pid, signal);
  } catch {}
}

/**
 * Any live process left in the run's group (the leader may exit before its children). Members must
 * have started no earlier than the leader, so a group id reused after a restart does not count.
 */
export function groupAlive(p: { pid: number; start: string }): boolean {
  try {
    process.kill(-p.pid, 0);
  } catch {
    return false;
  }
  const since = Number(p.start);
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    try {
      const stat = readFileSync(`/proc/${name}/stat`, "utf8");
      const f = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
      if (Number(f[2]) === p.pid && f[0] !== "Z" && Number(f[19]) >= since) return true;
    } catch {}
  }
  return false;
}

export function readExitFile(file: string): number | null {
  try {
    const n = Number.parseInt(readFileSync(file, "utf8").trim(), 10);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/** Write the per-run `docker` shim: a script that execs the orbit binary with the run's config. */
export function writeShim(
  binDir: string,
  configFile: string,
  shim: string[],
  cfg: ShimConfig,
): void {
  writeFileSync(configFile, `${JSON.stringify(cfg, null, 2)}\n`, { mode: 0o600 });
  const q = (s: string) => `'${s.replace(/'/g, "'\\''")}'`;
  const script = `#!/bin/sh\nexec ${[...shim, "__docker-shim", configFile].map(q).join(" ")} "$@"\n`;
  const file = join(binDir, "docker");
  writeFileSync(file, script, { mode: 0o755 });
  chmodSync(file, 0o755);
}

/** Docker client config of the daemon user (registry logins, CLI plugins such as buildx). */
export const dockerConfigDir = () => process.env.DOCKER_CONFIG || join(homedir(), ".docker");
