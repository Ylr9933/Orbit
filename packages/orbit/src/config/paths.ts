import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const DEFAULT_PORT = 7717;

export interface OrbitPaths {
  home: string;
  /** Daemon port on 127.0.0.1 (`ORBIT_PORT`, default 7717). */
  port: number;
  /** JSON `{ url, token, pid }` written by the running daemon (0600). */
  daemonFile: string;
  daemonLog: string;
  db: string;
  /** Auth profiles with their secrets (0600, daemon-owned). */
  auth: string;
  /** Notification targets (0600). */
  notify: string;
  /** Short-lived private files such as `docker run --env-file` inputs (0700). */
  tmp: string;
  /** Registered benchmarks (benchmarks.json). */
  benchmarks: string;
  /** Per-trial staging copies mounted into bench runs: `bench/<job>/<trial>` (0700). */
  bench: string;
  /** Per-run directories: `runs/<id>/{workspace,orbit/output,orbit/metrics.jsonl,log.txt,code.diff}`. */
  runs: string;
}

export function orbitPaths(env: NodeJS.ProcessEnv = process.env): OrbitPaths {
  const home = env.ORBIT_HOME || join(homedir(), ".orbit");
  return {
    home,
    port: Number(env.ORBIT_PORT) || DEFAULT_PORT,
    daemonFile: join(home, "daemon.json"),
    daemonLog: join(home, "daemon.log"),
    db: join(home, "orbit.db"),
    runs: join(home, "runs"),
    auth: join(home, "auth.json"),
    notify: join(home, "notify.json"),
    tmp: join(home, "tmp"),
    benchmarks: join(home, "benchmarks.json"),
    bench: join(home, "bench"),
  };
}

export function ensureHome(paths: OrbitPaths): void {
  mkdirSync(paths.home, { recursive: true, mode: 0o700 });
  mkdirSync(paths.runs, { recursive: true });
  mkdirSync(paths.tmp, { recursive: true, mode: 0o700 });
  mkdirSync(paths.bench, { recursive: true, mode: 0o700 });
}

export interface RunDirs {
  root: string;
  /** Code snapshot, mounted at /workspace. */
  workspace: string;
  /** Mounted at /orbit; holds output/ and metrics.jsonl. */
  orbit: string;
  output: string;
  metrics: string;
  log: string;
  diff: string;
  /** Agent CLI homes (`CODEX_HOME`, `CLAUDE_CONFIG_DIR`) under /orbit/agent; kept with the run. */
  agent: string;
}

export function runDirs(paths: OrbitPaths, runId: string): RunDirs {
  const root = join(paths.runs, runId);
  const orbit = join(root, "orbit");
  return {
    root,
    workspace: join(root, "workspace"),
    orbit,
    output: join(orbit, "output"),
    metrics: join(orbit, "metrics.jsonl"),
    log: join(root, "log.txt"),
    diff: join(root, "code.diff"),
    agent: join(orbit, "agent"),
  };
}
