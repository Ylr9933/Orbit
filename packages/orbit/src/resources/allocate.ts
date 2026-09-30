import type { Lease, NodeResources, ResourceRequest } from "../contracts/index.ts";

/** Keep this fraction of host memory out of leases for the OS and the daemon. */
export const MEM_LEASABLE_FRACTION = 0.9;

export type Allocation = { ok: true; gpuIds: string[] } | { ok: false; reason: string };

/** Reject requests this node can never satisfy (instead of queueing forever). */
export function infeasible(req: ResourceRequest, r: NodeResources): string | null {
  if (req.gpus > 0 && r.gpuError) return `GPUs requested but unavailable: ${r.gpuError}`;
  const fitting = r.gpus.filter(
    (g) =>
      (!req.gpuMemGB || g.memTotalMiB >= req.gpuMemGB * 1024) &&
      (!req.gpuIds?.length || matchesId(g, req.gpuIds)),
  );
  if (req.gpus > fitting.length) {
    return `needs ${req.gpus} GPU(s) but this node has ${fitting.length} matching`;
  }
  if (req.cpus > r.cpu.count) return `needs ${req.cpus} CPUs but this node has ${r.cpu.count}`;
  const maxMem = Math.floor(r.memory.totalGB * MEM_LEASABLE_FRACTION);
  if (req.memGB > maxMem)
    return `needs ${req.memGB} GB memory but at most ${maxMem} GB is leasable`;
  return null;
}

function matchesId(g: { uuid: string; index: number }, ids: string[]): boolean {
  return ids.some((id) => id === g.uuid || id === String(g.index));
}

/**
 * Decide whether `req` fits now.
 * available = probed hardware − active Orbit leases − external use (GPUs busy outside Orbit).
 */
export function allocate(req: ResourceRequest, r: NodeResources, leases: Lease[]): Allocation {
  const leasedCpus = leases.reduce((n, l) => n + l.cpus, 0);
  if (leasedCpus + req.cpus > r.cpu.count) {
    return { ok: false, reason: `waiting for CPUs (${r.cpu.count - leasedCpus}/${req.cpus} free)` };
  }
  const leasedMem = leases.reduce((n, l) => n + l.memGB, 0);
  const leasable = r.memory.totalGB * MEM_LEASABLE_FRACTION - leasedMem;
  if (req.memGB > leasable || req.memGB > r.memory.availableGB) {
    const free = Math.floor(Math.min(leasable, r.memory.availableGB));
    return { ok: false, reason: `waiting for memory (${free}/${req.memGB} GB free)` };
  }
  if (req.gpus === 0) return { ok: true, gpuIds: [] };

  const leased = new Set(leases.flatMap((l) => l.gpuIds));
  const free = r.gpus
    .filter((g) => !leased.has(g.uuid) && g.available)
    .filter((g) => !req.gpuMemGB || g.memTotalMiB >= req.gpuMemGB * 1024)
    .filter((g) => !req.gpuIds?.length || matchesId(g, req.gpuIds))
    .sort((a, b) => a.memUsedMiB - b.memUsedMiB || a.index - b.index);
  if (free.length < req.gpus) {
    const external = r.gpus.filter((g) => !leased.has(g.uuid) && !g.available).length;
    const why = external > 0 ? `, ${external} busy outside Orbit` : "";
    return { ok: false, reason: `waiting for GPUs (${free.length}/${req.gpus} free${why})` };
  }
  return { ok: true, gpuIds: free.slice(0, req.gpus).map((g) => g.uuid) };
}
