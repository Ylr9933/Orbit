// Resource use of a running run, sampled every few seconds: memory and CPU from the cgroup of each
// container (cgroup v2) or from /proc for a process group, GPU memory from nvidia-smi matched to the
// run's host pids. Peaks are kept in memory and folded into `Run.usage` by RunService.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { RunUsage } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";

const GIB = 1024 ** 3;
const CGROUP_ROOT = "/sys/fs/cgroup";
const round2 = (n: number) => Math.round(n * 100) / 100;
/** Memory in GB to the MB. */
const round3 = (n: number) => Math.round(n * 1000) / 1000;

const read = (f: string): string | null => {
  try {
    return readFileSync(f, "utf8");
  } catch {
    return null;
  }
};

/** cgroup v2 directory of a process (`0::/path` in /proc/<pid>/cgroup), or null. */
export function cgroupOf(pid: number, root = CGROUP_ROOT, proc = "/proc"): string | null {
  const text = read(join(proc, String(pid), "cgroup"));
  const line = text?.split("\n").find((l) => l.startsWith("0::"));
  return line ? join(root, line.slice(3).trim()) : null;
}

/** `key value` lines (memory.events, cpu.stat) as numbers. */
export function parseKeyed(text: string | null): Record<string, number> {
  const out: Record<string, number> = {};
  for (const line of (text ?? "").split("\n")) {
    const [k, v] = line.trim().split(/\s+/);
    if (k && v !== undefined && Number.isFinite(Number(v))) out[k] = Number(v);
  }
  return out;
}

export interface CgroupReading {
  memBytes: number;
  /** Peak since the cgroup was created (kernel ≥ 5.19), else the current value. */
  peakBytes: number;
  cpuUsec: number;
  oomKills: number;
  pids: number[];
}

export function readCgroup(dir: string): CgroupReading | null {
  const current = read(join(dir, "memory.current"));
  if (current === null) return null;
  const memBytes = Number(current.trim()) || 0;
  const peak = Number(read(join(dir, "memory.peak"))?.trim());
  return {
    memBytes,
    peakBytes: Number.isFinite(peak) && peak > 0 ? peak : memBytes,
    cpuUsec: parseKeyed(read(join(dir, "cpu.stat"))).usage_usec ?? 0,
    oomKills: parseKeyed(read(join(dir, "memory.events"))).oom_kill ?? 0,
    pids: (read(join(dir, "cgroup.procs")) ?? "")
      .split("\n")
      .map(Number)
      .filter((n) => n > 0),
  };
}

export interface ProcReading {
  rssBytes: number;
  /** utime + stime of the live members, in clock ticks. */
  cpuTicks: number;
  pids: number[];
}

/** RSS and CPU time of the live processes in process group `pgid` (started at or after `since`). */
export function readProcessGroup(pgid: number, since: number, proc = "/proc"): ProcReading {
  const page = 4096;
  let rssBytes = 0;
  let cpuTicks = 0;
  const pids: number[] = [];
  let names: string[] = [];
  try {
    names = readdirSync(proc);
  } catch {}
  for (const name of names) {
    if (!/^\d+$/.test(name)) continue;
    const stat = read(join(proc, name, "stat"));
    if (!stat) continue;
    const f = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
    if (Number(f[2]) !== pgid || f[0] === "Z" || Number(f[19]) < since) continue;
    pids.push(Number(name));
    cpuTicks += (Number(f[11]) || 0) + (Number(f[12]) || 0);
    rssBytes += (Number(f[21]) || 0) * page;
  }
  return { rssBytes, cpuTicks, pids };
}

/** `nvidia-smi --query-compute-apps=pid,used_memory` → MiB per pid. */
export function parseGpuApps(csv: string): Map<number, number> {
  const out = new Map<number, number>();
  for (const line of csv.split("\n")) {
    const [pid, mem] = line.split(",").map((s) => Number(s.trim()));
    if (pid && Number.isFinite(mem)) out.set(pid, (out.get(pid) ?? 0) + (mem as number));
  }
  return out;
}

let gpuCache: { at: number; apps: Promise<Map<number, number> | null> } | null = null;

/** GPU memory per host pid, shared by all samplers for two seconds; null without nvidia-smi. */
function gpuApps(): Promise<Map<number, number> | null> {
  if (!gpuCache || Date.now() - gpuCache.at > 2000)
    gpuCache = {
      at: Date.now(),
      apps: exec("nvidia-smi", [
        "--query-compute-apps=pid,used_memory",
        "--format=csv,noheader,nounits",
      ]).then((r) => (r.code === 0 ? parseGpuApps(r.stdout) : null)),
    };
  return gpuCache.apps;
}

/** What a run consists of at one sampling moment. */
export interface Targets {
  /** cgroup directories of its containers. */
  cgroups: string[];
  /** Its host process group (process runs). */
  group: { pgid: number; since: number } | null;
  gpus: boolean;
}

/** Peaks and means of one run; `add` folds in one reading. */
export class UsageMeter {
  usage: RunUsage;
  /** Readings that found anything of the run (it may end before the first one). */
  readings = 0;
  private last: { at: number; cpu: number } | null = null;
  private cpuSum = 0;
  private readonly oomSeen = new Map<string, number>();

  constructor(prev: RunUsage | null) {
    this.usage = prev
      ? { ...prev }
      : {
          samples: 0,
          peakMemGB: 0,
          peakCpus: 0,
          meanCpus: 0,
          peakGpuMemGB: null,
          oomKills: 0,
          oomKilled: false,
        };
    this.cpuSum = this.usage.meanCpus * this.usage.samples;
  }

  async sample(t: Targets, now = Date.now(), ticksPerSec = 100): Promise<void> {
    let mem = 0;
    let peak = 0;
    let cpuSec = 0;
    const pids: number[] = [];
    let found = 0;
    for (const dir of t.cgroups) {
      const r = readCgroup(dir);
      if (!r) continue;
      found += 1;
      mem += r.memBytes;
      peak += r.peakBytes;
      cpuSec += r.cpuUsec / 1e6;
      pids.push(...r.pids);
      // Counters are per container since its start; containers that are gone keep their last count.
      this.oomSeen.set(dir, Math.max(this.oomSeen.get(dir) ?? 0, r.oomKills));
    }
    // After a daemon restart the same counters are read again: never add them twice.
    const kills = [...this.oomSeen.values()].reduce((a, b) => a + b, 0);
    this.usage.oomKills = Math.max(this.usage.oomKills, kills);
    if (t.group) {
      const g = readProcessGroup(t.group.pgid, t.group.since);
      mem += g.rssBytes;
      peak += g.rssBytes;
      cpuSec += g.cpuTicks / ticksPerSec;
      pids.push(...g.pids);
      found += g.pids.length;
    }
    if (found === 0) return;
    this.readings += 1;
    const u = this.usage;
    u.peakMemGB = round3(Math.max(u.peakMemGB, peak / GIB, mem / GIB));
    if (this.last && now > this.last.at) {
      // A member that exited takes its CPU time along: never count that as negative use.
      const cpus = Math.max(0, (cpuSec - this.last.cpu) / ((now - this.last.at) / 1000));
      u.peakCpus = round2(Math.max(u.peakCpus, cpus));
      this.cpuSum += cpus;
      u.samples += 1;
      u.meanCpus = round2(this.cpuSum / u.samples);
    }
    this.last = { at: now, cpu: cpuSec };
    if (t.gpus) {
      const apps = await gpuApps();
      if (apps) {
        const mib = pids.reduce((s, p) => s + (apps.get(p) ?? 0), 0);
        u.peakGpuMemGB = round3(Math.max(u.peakGpuMemGB ?? 0, mib / 1024));
      }
    }
  }
}

/**
 * Samples a run until stopped. `targets` is re-read every time (containers come and go in process
 * runs); a failing read only skips that sample.
 */
export class UsageSampler {
  readonly meter: UsageMeter;
  private timer: NodeJS.Timeout | null = null;
  private running: Promise<void> | null = null;
  private readonly targets: () => Promise<Targets>;
  private readonly onSample: (u: RunUsage) => void;

  constructor(
    prev: RunUsage | null,
    targets: () => Promise<Targets>,
    onSample: (u: RunUsage) => void,
    everyMs: number,
  ) {
    this.meter = new UsageMeter(prev);
    this.targets = targets;
    this.onSample = onSample;
    this.timer = setInterval(() => void this.tick(), everyMs);
    this.timer.unref();
    void this.tick();
  }

  /** Take a sample now (unless one is in progress); resolves when it is done. */
  tick(): Promise<void> {
    this.running ??= (async () => {
      try {
        await this.meter.sample(await this.targets());
        this.onSample(this.meter.usage);
      } catch {
      } finally {
        this.running = null;
      }
    })();
    return this.running;
  }

  /** One last sample (short runs may end between ticks), then stop. */
  async stop(): Promise<RunUsage> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    await this.tick();
    return this.meter.usage;
  }

  /** Stop without sampling (daemon shutdown). */
  halt(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
