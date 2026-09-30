import { readFile, statfs } from "node:fs/promises";
import { availableParallelism, hostname, loadavg } from "node:os";
import type { Gpu, NodeResources } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";

/** A GPU is busy when processes outside Orbit hold more than this much memory. */
export const EXTERNAL_BUSY_MIB = 1024;

const GIB = 1024 ** 3;
const round1 = (n: number) => Math.round(n * 10) / 10;

interface RawGpu {
  index: number;
  uuid: string;
  name: string;
  memTotalMiB: number;
  memUsedMiB: number;
  utilPct: number | null;
}

function num(s: string | undefined): number | null {
  const n = Number(s?.trim());
  return s === undefined || Number.isNaN(n) ? null : n;
}

/** Parse `nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu`. */
export function parseGpuCsv(csv: string): RawGpu[] {
  return csv
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const [index, uuid, name, total, used, util] = line.split(",").map((f) => f.trim());
      const idx = num(index);
      const memTotal = num(total);
      if (idx === null || !uuid || memTotal === null) {
        throw new Error(`unexpected nvidia-smi line: ${line}`);
      }
      return {
        index: idx,
        uuid,
        name: name ?? "",
        memTotalMiB: memTotal,
        memUsedMiB: num(used) ?? 0,
        utilPct: num(util),
      };
    });
}

/** Parse `nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory`; returns MiB per GPU UUID. */
export function parseComputeApps(csv: string): Map<string, number> {
  const byGpu = new Map<string, number>();
  for (const line of csv.split("\n")) {
    const [uuid, , mem] = line.split(",").map((f) => f.trim());
    const mib = num(mem);
    if (!uuid || mib === null) continue;
    byGpu.set(uuid, (byGpu.get(uuid) ?? 0) + mib);
  }
  return byGpu;
}

/** Combine per-GPU memory with process usage. R0 has no leases, so every process is external. */
export function classifyGpus(raw: RawGpu[], appsMiB: Map<string, number>): Gpu[] {
  return raw.map((g) => {
    // Some drivers (e.g. in containers) hide processes; fall back to total used memory.
    const external = appsMiB.get(g.uuid) ?? g.memUsedMiB;
    return { ...g, externalMemMiB: external, available: external < EXTERNAL_BUSY_MIB };
  });
}

/** Parse `/proc/meminfo` into GB totals. */
export function parseMeminfo(text: string): { totalGB: number; availableGB: number } {
  const kb = (key: string) => {
    const m = text.match(new RegExp(`^${key}:\\s+(\\d+) kB`, "m"));
    return m?.[1] ? (Number(m[1]) * 1024) / GIB : 0;
  };
  return { totalGB: round1(kb("MemTotal")), availableGB: round1(kb("MemAvailable")) };
}

async function probeGpus(): Promise<{ gpus: Gpu[]; error: string | null }> {
  const q = await exec("nvidia-smi", [
    "--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu",
    "--format=csv,noheader,nounits",
  ]);
  if (q.code !== 0) return { gpus: [], error: q.stderr.trim() || `nvidia-smi exited ${q.code}` };
  const apps = await exec("nvidia-smi", [
    "--query-compute-apps=gpu_uuid,pid,used_memory",
    "--format=csv,noheader,nounits",
  ]);
  try {
    const appsMiB = apps.code === 0 ? parseComputeApps(apps.stdout) : new Map<string, number>();
    return { gpus: classifyGpus(parseGpuCsv(q.stdout), appsMiB), error: null };
  } catch (e) {
    return { gpus: [], error: (e as Error).message };
  }
}

/** Keep only the GPUs named by index or UUID (`ORBIT_GPUS`); null keeps all. */
export function filterGpus<T extends { index: number; uuid: string }>(
  gpus: T[],
  only: string[] | null,
): T[] {
  if (!only) return gpus;
  return gpus.filter((g) => only.includes(String(g.index)) || only.includes(g.uuid));
}

export async function probeNode(
  diskPath: string,
  opts: { node?: string; gpus?: string[] | null } = {},
): Promise<NodeResources> {
  const [gpu, meminfo, fs] = await Promise.all([
    probeGpus(),
    readFile("/proc/meminfo", "utf8"),
    statfs(diskPath),
  ]);
  return {
    node: opts.node ?? hostname(),
    probedAt: new Date().toISOString(),
    gpus: filterGpus(gpu.gpus, opts.gpus ?? null),
    gpuError: gpu.error,
    cpu: { count: availableParallelism(), load1: round1(loadavg()[0] ?? 0) },
    memory: parseMeminfo(meminfo),
    disk: {
      path: diskPath,
      totalGB: round1((fs.blocks * fs.bsize) / GIB),
      freeGB: round1((fs.bavail * fs.bsize) / GIB),
    },
  };
}
