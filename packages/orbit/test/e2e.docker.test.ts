// Real Docker end-to-end check. Opt in with ORBIT_E2E=1 (needs docker and python:3.12-slim;
// ORBIT_E2E_GPUS=1 also requests a GPU). Only touches containers labelled with this test's run ids.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { OrbitClient } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";

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
    git("init", "-q");
    git("add", ".");
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init");
    writeFileSync(join(proj, "untracked.txt"), "x");
    daemon = await startDaemon(orbitPaths({ ORBIT_HOME: home }), { port: 0, tickMs: 200 });
    client = new OrbitClient({ url: daemon.url, token: daemon.token, pid: process.pid });
  });
  afterAll(async () => {
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

  it("cancels a running container", async () => {
    const run = await client.submit({ ...spec(0), command: ["sleep", "300"] });
    for (let i = 0; i < 100 && (await client.get(run.id)).state !== "running"; i++)
      await new Promise((r) => setTimeout(r, 100));
    await client.cancel(run.id);
    const r = await finish(run.id);
    expect(r).toMatchObject({ state: "cancelled", cleanup: "done" });
  }, 120_000);
});
