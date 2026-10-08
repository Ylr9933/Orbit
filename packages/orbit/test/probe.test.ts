import { describe, expect, it } from "vitest";
import {
  describeCommand,
  parseBootTime,
  parseComputeApps,
  parseContainerId,
  parsePasswd,
  parseStartTicks,
  parseUid,
} from "../src/resources/gpu-procs.ts";
import { classifyGpus, parseGpuCsv, parseMeminfo } from "../src/resources/probe.ts";

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

  it("sums compute app memory per GPU, lists its processes and marks busy GPUs", () => {
    const apps = parseComputeApps("GPU-bbb, 11, 4000\nGPU-bbb, 12, 16000\nGPU-ccc, 13, 300\nbad\n");
    expect(apps).toHaveLength(3);
    const who = new Map([
      [
        12,
        {
          pid: 12,
          memMiB: 0,
          user: "alice",
          command: "python train.py",
          startedAt: "t",
          container: "c",
          runId: "r1",
        },
      ],
    ]);
    const gpus = classifyGpus(parseGpuCsv(GPUS), apps, who);
    expect(gpus.map((g) => g.available)).toEqual([true, false, true]);
    expect(gpus[1]?.externalMemMiB).toBe(20000);
    // Largest first; a process that could not be described keeps its pid and memory.
    expect(gpus[1]?.processes).toEqual([
      {
        pid: 12,
        memMiB: 16000,
        user: "alice",
        command: "python train.py",
        startedAt: "t",
        container: "c",
        runId: "r1",
      },
      {
        pid: 11,
        memMiB: 4000,
        user: null,
        command: null,
        startedAt: null,
        container: null,
        runId: null,
      },
    ]);
    // GPU without listed processes falls back to its used memory.
    expect(gpus[0]).toMatchObject({ externalMemMiB: 12, processes: [] });
  });

  it("describes a process from /proc without its arguments", () => {
    expect(parseUid("Name:\tpython\nUid:\t1023\t1023\t1023\t1023\n")).toBe(1023);
    const stat = `4242 (my (odd) name) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 987654 rest`;
    expect(parseStartTicks(stat)).toBe(987654);
    expect(parseBootTime("cpu 1 2\nbtime 1700000000\n")).toBe(1700000000);
    const id = "a".repeat(64);
    expect(parseContainerId(`0::/system.slice/docker-${id}.scope\n`)).toBe(id);
    expect(parseContainerId(`12:memory:/docker/${id}\n`)).toBe(id);
    expect(parseContainerId("0::/user.slice/user-1023.slice\n")).toBeNull();
    expect(
      parsePasswd("root:x:0:0::/root:/bin/bash\nbob:x:1023:1023::/home/bob:/bin/sh\n").get(1023),
    ).toBe("bob");
    expect(
      describeCommand("python", ["/usr/bin/python", "-u", "/w/train.py", "--api-key=SECRET"]),
    ).toBe("python train.py");
    expect(
      describeCommand("python3", ["python3", "-m", "vllm.entrypoints.api_server", "--token", "x"]),
    ).toBe("python3 -m vllm.entrypoints.api_server");
    expect(describeCommand("ollama", ["ollama", "serve"])).toBe("ollama");
  });

  it("parses /proc/meminfo", () => {
    const m = parseMeminfo(
      "MemTotal:       16777216 kB\nMemFree: 1 kB\nMemAvailable:    8388608 kB\n",
    );
    expect(m).toEqual({ totalGB: 16, availableGB: 8 });
  });
});
