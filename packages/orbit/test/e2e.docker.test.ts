// Real Docker end-to-end check. Opt in with ORBIT_E2E=1 (needs docker and python:3.12-slim;
// ORBIT_E2E_GPUS=1 also requests a GPU). Only touches containers labelled with this test's run ids.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { OrbitClient } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";
import * as docker from "../src/executor/docker.ts";
import { probeNode } from "../src/resources/probe.ts";
import { UsageSampler } from "../src/runs/usage.ts";

const enabled = process.env.ORBIT_E2E === "1";
const gpus = process.env.ORBIT_E2E_GPUS === "1" ? 1 : 0;
const home = mkdtempSync(join(tmpdir(), "orbit-e2e-"));
const proj = join(home, "proj");
let daemon: StartedDaemon;
let client: OrbitClient;

describe.runIf(enabled)("docker end-to-end", () => {
  beforeAll(async () => {
    mkdirSync(proj);
    writeFileSync(
      join(proj, "t.py"),
      [
        "import json, os, sys",
        "with open(os.environ['ORBIT_METRICS'], 'a') as f:",
        "    for s in range(3): f.write(json.dumps({'step': s, 'loss': 1 / (s + 1)}) + '\\n')",
        "open(os.path.join(os.environ['ORBIT_OUTPUT'], 'out.txt'), 'w').write('ok')",
        "print('hello from', os.getcwd())",
        "sys.exit(int(sys.argv[1]))",
      ].join("\n"),
    );
    const git = (...a: string[]) => execFileSync("git", ["-C", proj, ...a], { stdio: "pipe" });
    writeFileSync(join(proj, "Dockerfile"), "FROM python:3.12-slim\nRUN echo v1 > /built\n");
    git("init", "-q");
    git("add", ".");
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init");
    writeFileSync(join(proj, "untracked.txt"), "x");
    const paths = orbitPaths({ ORBIT_HOME: home });
    // Four CPUs to lease, so a run can be held in the queue by another one.
    daemon = await startDaemon(paths, {
      port: 0,
      tickMs: 200,
      self: [process.execPath, fileURLToPath(new URL("../src/bin.ts", import.meta.url))],
      probe: async () => ({
        ...(await probeNode(paths.data, { node: paths.node })),
        cpu: { count: 4, load1: 0, busy: 0 },
      }),
    });
    client = new OrbitClient({ url: daemon.url, token: daemon.token, pid: process.pid });
  });
  afterAll(async () => {
    if (client)
      await vi.waitFor(
        async () => {
          expect(
            (await client.list({ limit: 1000 })).every(
              (r) => r.cleanup !== "pending" && r.sizeBytes !== null,
            ),
          ).toBe(true);
        },
        { timeout: 10_000 },
      );
    await daemon?.stop();
    rmSync(home, { recursive: true, force: true });
  });

  const spec = (code: number) => ({
    project: proj,
    image: "python:3.12-slim",
    command: ["python", "t.py", String(code)],
    resources: { gpus, cpus: 1, memGB: 2 },
  });
  const finish = async (id: string) => {
    let r = await client.get(id);
    while (r.state !== "succeeded" && r.state !== "failed" && r.state !== "cancelled")
      r = await client.wait(id, 30);
    while (r.cleanup === "pending") r = await client.wait(id, 5);
    return r;
  };

  it("runs a snapshot, records metrics, artifacts and logs, and cleans up", async () => {
    const r = await finish((await client.submit(spec(0))).id);
    expect(r.state).toBe("succeeded");
    expect(r.cleanup).toBe("done");
    expect(r.lease?.state).toBe("released");
    expect(r.code?.changedFiles).toEqual(["untracked.txt"]);
    expect((await client.logs(r.id, 0)).text).toContain("hello from /workspace");
    expect((await client.metrics(r.id)).summary.loss).toBeCloseTo(1 / 3);
    expect((await client.artifacts(r.id)).files.map((f) => f.path)).toEqual(["out.txt"]);
    expect(readFileSync(join(home, "runs", r.id, "orbit/output/out.txt"), "utf8")).toBe("ok");
  }, 120_000);

  it("keeps evidence for failures", async () => {
    const r = await finish((await client.submit(spec(3))).id);
    expect(r).toMatchObject({ state: "failed", exitCode: 3, cleanup: "done" });
    expect((await client.metrics(r.id)).series).toHaveLength(1);
  }, 120_000);

  it("builds from the snapshot's Dockerfile and records the image id", async () => {
    const blocker = await client.submit({
      ...spec(0),
      command: ["sleep", "300"],
      resources: { cpus: 4, memGB: 1 },
    });
    const run = await client.submit({
      ...spec(0),
      image: undefined,
      dockerfile: "Dockerfile",
      command: ["cat", "/built"],
    });
    expect(run.state).toBe("queued");
    // Edited after submission: the run must still build what was snapshotted.
    writeFileSync(join(proj, "Dockerfile"), "FROM python:3.12-slim\nRUN echo v2 > /built\n");
    await client.cancel(blocker.id);
    const r = await finish(run.id);
    writeFileSync(join(proj, "Dockerfile"), "FROM python:3.12-slim\nRUN echo v1 > /built\n");
    expect(r.state, r.reason ?? "").toBe("succeeded");
    expect(readFileSync(join(home, "runs", r.id, "log.txt"), "utf8")).toMatch(/^v1$/m);
    expect(r.image).toMatch(/^orbit-local\/proj:/);
    expect(r.imageId).toMatch(/^sha256:[0-9a-f]{64}$/);
    const events = (await client.events(r.id)).map((e) => e.message);
    expect(events.some((m) => m.includes("building from the code snapshot"))).toBe(true);
    await finish(blocker.id);
  }, 300_000);

  it.each([0, 7])(
    "preserves exit %i while Docker artifact collection crosses the deadline",
    async (code) => {
      const copy = docker.copyFromContainer;
      const delayed = vi.spyOn(docker, "copyFromContainer").mockImplementation(async (...args) => {
        // A controlled collection delay around real Docker IO, not a fake executor.
        await new Promise((r) => setTimeout(r, 6500));
        return copy(...args);
      });
      try {
        const run = await finish(
          (
            await client.submit({
              ...spec(code),
              command: [
                "sh",
                "-c",
                `echo 'background request timed out'; echo ok > /tmp/evidence; exit ${code}`,
              ],
              timeoutMin: 0.1,
              collect: ["/tmp/evidence"],
            })
          ).id,
        );
        expect(run).toMatchObject({
          state: code === 0 ? "succeeded" : "failed",
          exitCode: code,
          reason: code === 0 ? null : "exit code 7",
          cleanup: "done",
        });
        expect(run.lease?.state).toBe("released");
        expect(
          readFileSync(join(home, "runs", run.id, "orbit/output/collected/tmp/evidence"), "utf8"),
        ).toBe("ok\n");
        expect((await client.logs(run.id, 0)).text).toContain("background request timed out");
        expect((await client.events(run.id)).some((e) => e.kind === "timeout")).toBe(false);
      } finally {
        delayed.mockRestore();
      }
    },
    120_000,
  );

  it.each([0, 7])(
    "preserves exit %i while process usage collection crosses the deadline",
    async (code) => {
      const stop = UsageSampler.prototype.stop;
      const delayed = vi.spyOn(UsageSampler.prototype, "stop").mockImplementation(async function (
        this: UsageSampler,
      ) {
        await new Promise((r) => setTimeout(r, 6500));
        return stop.call(this);
      });
      try {
        const run = await finish(
          (
            await client.submit({
              backend: "process",
              command: ["sh", "-c", `echo 'background request timed out'; exit ${code}`],
              resources: { cpus: 1, memGB: 1 },
              timeoutMin: 0.1,
            })
          ).id,
        );
        expect(run).toMatchObject({
          state: code === 0 ? "succeeded" : "failed",
          exitCode: code,
          reason: code === 0 ? null : "exit code 7",
          cleanup: "done",
        });
        expect(run.lease?.state).toBe("released");
        expect((await client.events(run.id)).some((e) => e.kind === "timeout")).toBe(false);
      } finally {
        delayed.mockRestore();
      }
    },
    120_000,
  );

  it.each(["docker", "process"] as const)(
    "still terminates a genuinely timed-out %s run",
    async (backend) => {
      const run = await finish(
        (
          await client.submit({
            backend,
            ...(backend === "docker" ? { image: "python:3.12-slim" } : {}),
            command: ["sleep", "300"],
            resources: { cpus: 1, memGB: 1 },
            timeoutMin: 0.02,
          })
        ).id,
      );
      expect(run).toMatchObject({
        state: "failed",
        reason: "timeout after 0.02 min",
        cleanup: "done",
      });
      expect(run.lease?.state).toBe("released");
      expect((await client.events(run.id)).filter((e) => e.kind === "timeout")).toHaveLength(1);
    },
    120_000,
  );

  it("cancels a running container", async () => {
    const run = await client.submit({ ...spec(0), command: ["sleep", "300"] });
    for (let i = 0; i < 100 && (await client.get(run.id)).state !== "running"; i++)
      await new Promise((r) => setTimeout(r, 100));
    await client.cancel(run.id);
    const r = await finish(run.id);
    expect(r).toMatchObject({ state: "cancelled", cleanup: "done" });
  }, 120_000);
});
