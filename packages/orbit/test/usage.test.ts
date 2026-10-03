// Resource sampling from cgroup v2 files, /proc and nvidia-smi output (fixtures, no live system).
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import {
  cgroupOf,
  parseGpuApps,
  parseKeyed,
  readCgroup,
  readProcessGroup,
  UsageMeter,
} from "../src/runs/usage.ts";

const tmp = mkdtempSync(join(tmpdir(), "orbit-usage-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));
const put = (file: string, text: string) => {
  mkdirSync(join(file, ".."), { recursive: true });
  writeFileSync(file, text);
};
const GIB = 1024 ** 3;

/** A container cgroup with memory, CPU and OOM counters. */
function cgroup(name: string, cur: number, peak: number, usec: number, kills = 0, pids = "7\n") {
  const d = join(tmp, "cg", name);
  put(join(d, "memory.current"), `${cur}\n`);
  put(join(d, "memory.peak"), `${peak}\n`);
  put(join(d, "cpu.stat"), `usage_usec ${usec}\nuser_usec 1\n`);
  put(join(d, "memory.events"), `low 0\nhigh 0\nmax 2\noom ${kills}\noom_kill ${kills}\n`);
  put(join(d, "cgroup.procs"), pids);
  return d;
}

/** /proc/<pid>/stat with pgrp, start time and rss (pages) at their field positions. */
function procStat(pid: number, pgrp: number, start: number, rss: number, utime = 0, state = "S") {
  const f = Array(40).fill("0");
  f[0] = state;
  f[2] = String(pgrp);
  f[11] = String(utime);
  f[12] = "0";
  f[19] = String(start);
  f[21] = String(rss);
  put(join(tmp, "proc", String(pid), "stat"), `${pid} (py (x)) ${f.join(" ")}\n`);
}

describe("usage sampling", () => {
  it("parses cgroup files, process groups and nvidia-smi", () => {
    expect(parseKeyed("usage_usec 10\nbad\noom_kill 2\n")).toEqual({ usage_usec: 10, oom_kill: 2 });
    put(join(tmp, "p", "42", "cgroup"), "0::/system.slice/docker-abc.scope\n");
    expect(cgroupOf(42, "/sys/fs/cgroup", join(tmp, "p"))).toBe(
      "/sys/fs/cgroup/system.slice/docker-abc.scope",
    );
    expect(cgroupOf(43, "/r", join(tmp, "p"))).toBeNull();
    const d = cgroup("a", 2 * GIB, 3 * GIB, 5e6, 1, "7\n8\n");
    expect(readCgroup(d)).toEqual({
      memBytes: 2 * GIB,
      peakBytes: 3 * GIB,
      cpuUsec: 5e6,
      oomKills: 1,
      pids: [7, 8],
    });
    expect(readCgroup(join(tmp, "missing"))).toBeNull();
    procStat(100, 100, 500, 1000, 50);
    procStat(101, 100, 600, 3000, 20);
    procStat(102, 100, 400, 9999); // started before the leader: a reused group id, not ours
    procStat(103, 999, 600, 9999);
    procStat(104, 100, 600, 9999, 0, "Z");
    expect(readProcessGroup(100, 500, join(tmp, "proc"))).toEqual({
      rssBytes: 4000 * 4096,
      cpuTicks: 70,
      pids: [100, 101],
    });
    expect(parseGpuApps("7, 1320\n8, 100\n7, 10\nbad\n")).toEqual(
      new Map([
        [7, 1330],
        [8, 100],
      ]),
    );
  });

  it("keeps peaks, CPU rate from deltas and OOM kills without double counting", async () => {
    const d = cgroup("b", 1 * GIB, 1 * GIB, 0);
    const m = new UsageMeter(null);
    const t = { cgroups: [d], group: null, gpus: false };
    await m.sample(t, 0);
    expect(m.usage).toMatchObject({ samples: 0, peakMemGB: 1 });
    expect(m.readings).toBe(1);
    const gone = new UsageMeter(null);
    await gone.sample({ cgroups: [join(tmp, "removed")], group: null, gpus: false }, 0);
    expect(gone.readings).toBe(0);
    cgroup("b", 0.5 * GIB, 6 * GIB, 4e6, 1);
    await m.sample(t, 2000);
    expect(m.usage).toMatchObject({
      samples: 1,
      peakMemGB: 6,
      peakCpus: 2,
      meanCpus: 2,
      oomKills: 1,
    });
    cgroup("b", 0.5 * GIB, 6 * GIB, 5e6, 1);
    await m.sample(t, 4000);
    expect(m.usage).toMatchObject({ samples: 2, peakCpus: 2, meanCpus: 1.25, oomKills: 1 });
    // After a daemon restart the same counters are read again by a meter seeded with the old usage.
    const again = new UsageMeter(m.usage);
    await again.sample(t, 10_000);
    expect(again.usage).toMatchObject({ oomKills: 1, samples: 2, peakMemGB: 6 });
  });
});
