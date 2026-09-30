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
  };
}

export function ensureHome(paths: OrbitPaths): void {
  mkdirSync(paths.home, { recursive: true, mode: 0o700 });
  mkdirSync(paths.runs, { recursive: true });
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
  };
}
