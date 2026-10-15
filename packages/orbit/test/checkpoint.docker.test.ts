// Opt-in real Docker test. No model calls; session data is an explicit fixture.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { OrbitClient } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";
import * as docker from "../src/executor/docker.ts";

const home = mkdtempSync(join(tmpdir(), "orbit-checkpoint-real-"));
const paths = orbitPaths({ ORBIT_HOME: home });
let daemon: StartedDaemon;
let client: OrbitClient;
const image = process.env.ORBIT_CHECKPOINT_IMAGE ?? "python:3.11-slim-bookworm";
const finish = async (id: string) => {
  let run = await client.get(id);
  while (
    !["succeeded", "failed", "cancelled", "lost"].includes(run.state) ||
    run.cleanup === "pending"
  )
    run = await client.wait(id, 10);
  return run;
};

describe.runIf(process.env.ORBIT_E2E === "1")("real Docker checkpoints", () => {
  beforeAll(async () => {
    daemon = await startDaemon(paths, { port: 0, tickMs: 100 });
    client = new OrbitClient({ url: daemon.url, token: daemon.token, pid: process.pid });
  });
  afterAll(async () => {
    if (client) {
      const runs = await client.list({ limit: 1000 });
      for (const r of runs) {
        if (["queued", "starting", "running"].includes(r.state)) {
          await client.cancel(r.id);
          await finish(r.id);
        }
      }
      for (const r of runs)
        if (r.checkpoint?.imageId) await docker.removeCheckpoint(`orbit-checkpoint/${r.id}:saved`);
    }
    await daemon?.stop();
    rmSync(home, { recursive: true, force: true });
  });

  it("restores a killed task's files offline after cleanup and a daemon restart, before any verifier contamination", async () => {
    const project = join(home, "project");
    mkdirSync(project);
    writeFileSync(join(project, "seed"), "input");
    for (const argv of [
      ["init", "-q"],
      ["add", "."],
      [
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-qm",
        "fixture",
      ],
    ])
      execFileSync("git", ["-C", project, ...argv]);
    process.env.ORBIT_CHECKPOINT_FIXTURE_KEY = "not-a-real-key";
    const run = await client.submit({
      image,
      project,
      root: true,
      network: false,
      resources: { cpus: 1, memGB: 1 },
      checkpoint: { maxSizeGB: 1 },
      passEnv: ["ORBIT_CHECKPOINT_FIXTURE_KEY"],
      command: [
        "sh",
        "-c",
        "echo filesystem > /tmp/orbit-progress; echo workspace > /workspace/progress; echo output > /orbit/output/progress; sleep 300",
      ],
      after: { command: ["sh", "-c", "touch /tmp/verifier-was-here"], timeoutMin: 1 },
    });
    let current = await client.get(run.id);
    await expect
      .poll(
        async () => {
          current = await client.get(run.id);
          return (
            Boolean(current.containerId) &&
            existsSync(join(daemon.runs.dirs(run.id).output, "progress"))
          );
        },
        { timeout: 30_000 },
      )
      .toBe(true);
    expect(readFileSync(join(daemon.runs.dirs(run.id).output, "progress"), "utf8")).toBe(
      "output\n",
    );
    execFileSync("docker", ["kill", current.containerId as string]);
    const failed = await finish(run.id);
    expect(failed).toMatchObject({
      state: "failed",
      cleanup: "done",
      lease: { state: "released" },
      checkpoint: { state: "ready" },
      after: { state: "skipped" },
    });
    expect(await docker.inspectContainer(current.containerId as string)).toBeNull();
    const env = JSON.parse(
      execFileSync("docker", ["image", "inspect", failed.checkpoint?.imageId as string], {
        encoding: "utf8",
      }),
    )[0].Config.Env as string[];
    expect(env).not.toContain("ORBIT_CHECKPOINT_FIXTURE_KEY=not-a-real-key");
    await daemon.stop();
    daemon = await startDaemon(paths, { port: 0, tickMs: 100 });
    client = new OrbitClient({ url: daemon.url, token: daemon.token, pid: process.pid });
    const restored = await client.resume(run.id, {
      command: [
        "sh",
        "-c",
        "test ! -e /tmp/verifier-was-here && test ! -e /orbit/phases/main.exit && cat /tmp/orbit-progress /workspace/progress /orbit/output/progress && touch /orbit/output/restored; while test ! -e /orbit/output/release; do sleep 0.1; done",
      ],
    });
    await expect
      .poll(() => existsSync(join(daemon.runs.dirs(restored.id).output, "restored")), {
        timeout: 30_000,
      })
      .toBe(true);
    await expect(client.deleteRuns([run.id])).rejects.toThrow(
      "checkpoint is used by an active restored run",
    );
    writeFileSync(join(daemon.runs.dirs(restored.id).output, "release"), "");
    expect((await finish(restored.id)).state).toBe("succeeded");
    expect((await client.logs(restored.id, 0)).text).toContain("filesystem\nworkspace\noutput");
    expect(restored.spec.parentId).toBe(run.id);
    const deleted = await client.deleteRuns([run.id, restored.id]);
    expect(deleted.deleted).toHaveLength(2);
    expect(await docker.imageExists(failed.checkpoint?.imageId as string)).toBe(false);
    delete process.env.ORBIT_CHECKPOINT_FIXTURE_KEY;
  }, 120_000);

  it("keeps normal failure cleanup and artifacts when the checkpoint exceeds its limit", async () => {
    const run = await client.submit({
      image,
      root: true,
      network: false,
      resources: { cpus: 1, memGB: 1 },
      checkpoint: { maxSizeGB: 1e-9 },
      command: [
        "sh",
        "-c",
        "echo evidence > /orbit/output/evidence; echo state > /tmp/state; exit 7",
      ],
    });
    const ended = await finish(run.id);
    expect(ended).toMatchObject({
      state: "failed",
      exitCode: 7,
      cleanup: "done",
      lease: { state: "released" },
      checkpoint: { state: "failed", imageId: null },
    });
    expect(readFileSync(join(daemon.runs.dirs(run.id).output, "evidence"), "utf8")).toBe(
      "evidence\n",
    );
  }, 60_000);

  it("does not snapshot successful tasks", async () => {
    const run = await client.submit({
      image,
      network: false,
      resources: { cpus: 1, memGB: 1 },
      checkpoint: {},
      command: ["true"],
    });
    expect(await finish(run.id)).toMatchObject({
      state: "succeeded",
      cleanup: "done",
      checkpoint: null,
    });
  }, 60_000);
});
