import { describe, expect, it } from "vitest";
import {
  classifyGpus,
  parseComputeApps,
  parseGpuCsv,
  parseMeminfo,
} from "../src/resources/probe.ts";

const GPUS = `0, GPU-aaa, NVIDIA GeForce RTX 3090, 24576, 12, 0
1, GPU-bbb, NVIDIA GeForce RTX 3090, 24576, 20480, 97
2, GPU-ccc, NVIDIA GeForce RTX 3090, 24576, 900, [N/A]
`;

describe("resource probe parsing", () => {
  it("parses nvidia-smi GPU rows", () => {
    const gpus = parseGpuCsv(GPUS);
    expect(gpus).toHaveLength(3);
    expect(gpus[0]).toMatchObject({ index: 0, uuid: "GPU-aaa", memTotalMiB: 24576, utilPct: 0 });
    expect(gpus[2]?.utilPct).toBeNull();
  });

  it("rejects malformed rows instead of guessing", () => {
    expect(() => parseGpuCsv("garbage")).toThrow(/unexpected/);
  });

  it("sums compute app memory per GPU and marks busy GPUs", () => {
    const apps = parseComputeApps("GPU-bbb, 11, 10000\nGPU-bbb, 12, 10000\nGPU-ccc, 13, 300\n");
    expect(apps.get("GPU-bbb")).toBe(20000);
    const gpus = classifyGpus(parseGpuCsv(GPUS), apps);
    expect(gpus.map((g) => g.available)).toEqual([true, false, true]);
    // GPU without listed processes falls back to its used memory.
    expect(gpus[0]?.externalMemMiB).toBe(12);
  });

  it("parses /proc/meminfo", () => {
    const m = parseMeminfo(
      "MemTotal:       16777216 kB\nMemFree: 1 kB\nMemAvailable:    8388608 kB\n",
    );
    expect(m).toEqual({ totalGB: 16, availableGB: 8 });
  });
});
