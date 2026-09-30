import { describe, expect, it } from "vitest";
import type { Lease, NodeResources } from "../src/contracts/index.ts";
import { ResourceRequest } from "../src/contracts/index.ts";
import { allocate, infeasible } from "../src/resources/allocate.ts";

const gpu = (index: number, over: Partial<NodeResources["gpus"][number]> = {}) => ({
  index,
  uuid: `GPU-${index}`,
  name: "RTX 3090",
  memTotalMiB: 24576,
  memUsedMiB: 10,
  utilPct: 0,
  externalMemMiB: 10,
  available: true,
  ...over,
});

const node: NodeResources = {
  node: "n",
  probedAt: "",
  gpus: [
    gpu(0),
    gpu(1, { memUsedMiB: 5000, externalMemMiB: 5000, available: false }),
    gpu(2),
    gpu(3, { memUsedMiB: 500 }),
  ],
  gpuError: null,
  cpu: { count: 16, load1: 0 },
  memory: { totalGB: 100, availableGB: 80 },
  disk: { path: "/", totalGB: 1, freeGB: 1 },
};

const lease = (gpuIds: string[], cpus = 4, memGB = 16): Lease => ({
  id: "l",
  runId: "r",
  node: "n",
  gpuIds,
  cpus,
  memGB,
  state: "active",
  createdAt: "",
  releasedAt: null,
});

const req = (r: Partial<ResourceRequest>) => ResourceRequest.parse(r);

describe("allocate", () => {
  it("skips externally busy and leased GPUs, preferring the least used", () => {
    expect(allocate(req({ gpus: 2 }), node, [])).toEqual({ ok: true, gpuIds: ["GPU-0", "GPU-2"] });
    expect(allocate(req({ gpus: 1 }), node, [lease(["GPU-0"])])).toEqual({
      ok: true,
      gpuIds: ["GPU-2"],
    });
  });

  it("queues with a reason when GPUs are short", () => {
    const a = allocate(req({ gpus: 3 }), node, [lease(["GPU-0"])]);
    expect(a).toEqual({ ok: false, reason: "waiting for GPUs (2/3 free, 1 busy outside Orbit)" });
  });

  it("honours pinned GPUs by index or uuid", () => {
    expect(allocate(req({ gpus: 1, gpuIds: ["3"] }), node, [])).toEqual({
      ok: true,
      gpuIds: ["GPU-3"],
    });
    expect(allocate(req({ gpus: 1, gpuIds: ["GPU-1"] }), node, []).ok).toBe(false);
  });

  it("accounts CPU and memory leases", () => {
    expect(allocate(req({ cpus: 10 }), node, [lease([], 8)]).ok).toBe(false);
    expect(allocate(req({ memGB: 50 }), node, [lease([], 1, 50)]).ok).toBe(false);
    expect(allocate(req({ memGB: 85 }), node, []).ok).toBe(false); // above MemAvailable
  });

  it("rejects requests the node can never satisfy", () => {
    expect(infeasible(req({ gpus: 5 }), node)).toMatch(/has 4 matching/);
    expect(infeasible(req({ gpus: 1, gpuMemGB: 40 }), node)).toMatch(/has 0 matching/);
    expect(infeasible(req({ cpus: 32 }), node)).toMatch(/CPUs/);
    expect(infeasible(req({ gpus: 4 }), node)).toBeNull();
  });
});
