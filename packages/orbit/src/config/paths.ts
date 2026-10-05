import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir, hostname } from "node:os";
import { isAbsolute, join } from "node:path";

export const DEFAULT_PORT = 7717;

export interface OrbitPaths {
  /** Small state: database, profiles, daemon endpoint, config (`ORBIT_HOME`, default `~/.orbit`). */
  home: string;
  /**
   * Large data: run directories, bench staging and code bundles (`ORBIT_DATA`, else `dataDir` in
   * `<home>/config.json`, else `home`). Put it on a large disk.
   */
  data: string;
  /** Where `data` came from. */
  dataSource: "env" | "config" | "default";
  /** `<home>/config.json`: `{ dataDir? }`. */
  config: string;
  /** This node's name in a cluster (`ORBIT_NODE`, default: the hostname). */
  node: string;
  /** GPUs this daemon manages, by index or UUID (`ORBIT_GPUS`, comma-separated); null means all. */
  gpus: string[] | null;
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
  /** Named datasets / weights: name -> path on this node (datasets.json). */
  datasets: string;
  /** Worker nodes registered on this (primary) node, with their tokens (0600). */
  nodes: string;
  /** This node's cluster listener: address and token (0600). */
  cluster: string;
  /** Content-addressed code bundles received from a primary: `cache/bundles/<sha256>`. */
  bundles: string;
  /** Per-run directories: `runs/<id>/{workspace,orbit/output,orbit/metrics.jsonl,log.txt,code.diff}`. */
  runs: string;
}

export interface OrbitConfig {
  /** Absolute path of the data directory. */
  dataDir?: string;
}

export function readConfig(file: string): OrbitConfig {
  if (!existsSync(file)) return {};
  let v: unknown;
  try {
    v = JSON.parse(readFileSync(file, "utf8"));
  } catch {
    throw new Error(`${file} is not valid JSON`);
  }
  const dataDir = (v as OrbitConfig | null)?.dataDir;
  if (dataDir !== undefined && (typeof dataDir !== "string" || !isAbsolute(dataDir)))
    throw new Error(`${file}: dataDir must be an absolute path`);
  return dataDir ? { dataDir } : {};
}

export function writeConfig(file: string, c: OrbitConfig): void {
  writeFileSync(file, `${JSON.stringify(c, null, 2)}\n`, { mode: 0o600 });
}

export function orbitPaths(env: NodeJS.ProcessEnv = process.env): OrbitPaths {
  const home = env.ORBIT_HOME || join(homedir(), ".orbit");
  const config = join(home, "config.json");
  if (env.ORBIT_DATA && !isAbsolute(env.ORBIT_DATA))
    throw new Error("ORBIT_DATA must be an absolute path");
  const configured = readConfig(config).dataDir;
  const data = env.ORBIT_DATA || configured || home;
  const dataSource = env.ORBIT_DATA ? "env" : configured ? "config" : "default";
  const gpus = (env.ORBIT_GPUS ?? "")
    .split(",")
    .map((g) => g.trim())
    .filter(Boolean);
  return {
    home,
    data,
    dataSource,
    config,
    node: env.ORBIT_NODE || hostname(),
    gpus: gpus.length > 0 ? gpus : null,
    port: Number(env.ORBIT_PORT) || DEFAULT_PORT,
    daemonFile: join(home, "daemon.json"),
    daemonLog: join(home, "daemon.log"),
    db: join(home, "orbit.db"),
    runs: join(data, "runs"),
    auth: join(home, "auth.json"),
    notify: join(home, "notify.json"),
    tmp: join(home, "tmp"),
    benchmarks: join(home, "benchmarks.json"),
    bench: join(data, "bench"),
    datasets: join(home, "datasets.json"),
    nodes: join(home, "nodes.json"),
    cluster: join(home, "cluster.json"),
    bundles: join(data, "cache", "bundles"),
  };
}

export function ensureHome(paths: OrbitPaths): void {
  mkdirSync(paths.home, { recursive: true, mode: 0o700 });
  mkdirSync(paths.data, { recursive: true, mode: 0o700 });
  mkdirSync(paths.runs, { recursive: true });
  mkdirSync(paths.tmp, { recursive: true, mode: 0o700 });
  mkdirSync(paths.bench, { recursive: true, mode: 0o700 });
  mkdirSync(paths.bundles, { recursive: true });
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

/** Whether a directory is on the same filesystem as `/` (where a full disk takes the system down). */
export function onSystemDisk(dir: string): boolean {
  try {
    return statSync(dir).dev === statSync("/").dev;
  } catch {
    return false;
  }
}
