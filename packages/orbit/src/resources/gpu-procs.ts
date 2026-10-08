// Who holds GPU memory: the compute processes nvidia-smi lists, described from /proc (user, start
// time, process name and script) and Docker (container, Orbit run). Fields that cannot be read (a
// process in another PID namespace, gone meanwhile, or unreadable) are null and shown as unknown.
// Full command lines are not reported: they may carry secrets (e.g. `--api-key=...`).
import { readFile } from "node:fs/promises";
import type { GpuProcess } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";

export interface ComputeApp {
  uuid: string;
  pid: number;
  memMiB: number;
}

const int = (s: string | undefined) => {
  const n = Number(s?.trim());
  return s === undefined || s.trim() === "" || !Number.isFinite(n) ? null : n;
};

/** Parse `nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader,nounits`. */
export function parseComputeApps(csv: string): ComputeApp[] {
  const out: ComputeApp[] = [];
  for (const line of csv.split("\n")) {
    const [uuid, pid, mem] = line.split(",").map((f) => f.trim());
    const p = int(pid);
    const m = int(mem);
    if (uuid && p !== null && m !== null) out.push({ uuid, pid: p, memMiB: m });
  }
  return out;
}

/** The real uid from `/proc/<pid>/status`. */
export function parseUid(status: string): number | null {
  return int(/^Uid:\s+(\d+)/m.exec(status)?.[1]);
}

/** Start time in clock ticks after boot: field 22 of `/proc/<pid>/stat` (the name may hold spaces). */
export function parseStartTicks(stat: string): number | null {
  const rest = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
  // `rest` starts at field 3 (state), so field 22 is at index 19.
  return int(rest[19]);
}

/** Boot time (seconds since the epoch) from `/proc/stat`. */
export function parseBootTime(stat: string): number | null {
  return int(/^btime\s+(\d+)/m.exec(stat)?.[1]);
}

/** A Docker container id from `/proc/<pid>/cgroup` (cgroup v1 `/docker/<id>`, v2 `docker-<id>.scope`). */
export function parseContainerId(cgroup: string): string | null {
  return /(?:docker[-/]|\/docker\/)([0-9a-f]{64})/.exec(cgroup)?.[1] ?? null;
}

/** `name -> uid` lines of /etc/passwd as a uid lookup. */
export function parsePasswd(text: string): Map<number, string> {
  const m = new Map<number, string>();
  for (const line of text.split("\n")) {
    const [name, , uid] = line.split(":");
    const u = int(uid);
    if (name && u !== null && !m.has(u)) m.set(u, name);
  }
  return m;
}

const base = (p: string) => p.slice(p.lastIndexOf("/") + 1);

/**
 * What the process is, without its arguments: its name, plus the script or module it runs when
 * there is one (`python train.py`, `python -m vllm.entrypoints...`).
 */
export function describeCommand(comm: string, argv: string[]): string {
  const name = comm.trim() || base(argv[0] ?? "") || "?";
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "-m" && argv[i + 1]) return `${name} -m ${argv[i + 1]}`.slice(0, 120);
    if (a.startsWith("-")) continue;
    if (/\.(py|sh|js|ts|rb|pl|jl|R)$/.test(a)) return `${name} ${base(a)}`.slice(0, 120);
    break;
  }
  return name.slice(0, 120);
}

interface Containers {
  at: number;
  byId: Map<string, { name: string; runId: string | null }>;
}
let containers: Containers | null = null;
let passwd: { at: number; map: Map<number, string> } | null = null;
let clockTicks: number | null = null;
const CACHE_MS = 5000;

async function containerMap(): Promise<Containers["byId"]> {
  if (containers && Date.now() - containers.at < CACHE_MS) return containers.byId;
  const r = await exec("docker", [
    "ps",
    "--no-trunc",
    "--format",
    '{{.ID}}\t{{.Names}}\t{{.Label "orbit.run"}}',
  ]);
  const byId = new Map<string, { name: string; runId: string | null }>();
  if (r.code === 0)
    for (const line of r.stdout.split("\n")) {
      const [id, name, run] = line.split("\t");
      if (id && name) byId.set(id, { name, runId: run || null });
    }
  containers = { at: Date.now(), byId };
  return byId;
}

async function users(): Promise<Map<number, string>> {
  if (passwd && Date.now() - passwd.at < 60_000) return passwd.map;
  const text = await readFile("/etc/passwd", "utf8").catch(() => "");
  passwd = { at: Date.now(), map: parsePasswd(text) };
  return passwd.map;
}

async function ticksPerSecond(): Promise<number> {
  if (clockTicks === null) {
    const r = await exec("getconf", ["CLK_TCK"]);
    clockTicks = (r.code === 0 ? int(r.stdout) : null) ?? 100;
  }
  return clockTicks;
}

const read = (p: string) => readFile(p, "utf8").catch(() => null);

/** Describe compute processes; anything that cannot be read stays null. */
export async function describeProcesses(apps: ComputeApp[]): Promise<Map<number, GpuProcess>> {
  const out = new Map<number, GpuProcess>();
  if (apps.length === 0) return out;
  const [names, hz, procStat] = await Promise.all([users(), ticksPerSecond(), read("/proc/stat")]);
  const boot = procStat ? parseBootTime(procStat) : null;
  const pids = [...new Set(apps.map((a) => a.pid))];
  const raw = await Promise.all(
    pids.map(async (pid) => {
      const [status, stat, comm, cmdline, cgroup] = await Promise.all(
        ["status", "stat", "comm", "cmdline", "cgroup"].map((f) => read(`/proc/${pid}/${f}`)),
      );
      return { pid, status, stat, comm, cmdline, cgroup };
    }),
  );
  const ids = raw.map((p) => (p.cgroup ? parseContainerId(p.cgroup) : null));
  const docker = ids.some(Boolean) ? await containerMap() : new Map();
  raw.forEach((p, i) => {
    const uid = p.status ? parseUid(p.status) : null;
    const ticks = p.stat ? parseStartTicks(p.stat) : null;
    const id = ids[i];
    const c = id ? docker.get(id) : undefined;
    const argv = p.cmdline ? p.cmdline.split("\0").filter(Boolean) : [];
    out.set(p.pid, {
      pid: p.pid,
      memMiB: 0,
      user: uid === null ? null : (names.get(uid) ?? `uid ${uid}`),
      command: p.comm !== null || argv.length ? describeCommand(p.comm ?? "", argv) : null,
      startedAt:
        boot !== null && ticks !== null ? new Date((boot + ticks / hz) * 1000).toISOString() : null,
      container: c?.name ?? (id ? id.slice(0, 12) : null),
      runId: c?.runId ?? null,
    });
  });
  return out;
}
