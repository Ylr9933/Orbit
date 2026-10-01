// Two daemons in one process: a primary placing a run on a worker node over the cluster API. The
// `docker` on PATH is a fake that refuses every image, so the remote run fails at image preparation
// on the worker; this checks registration, authentication, code transfer, placement and mirroring
// without touching Docker. Real containers across nodes are an operator check (docs/guides/multi-node.md).
import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { type OrbitClient, tryConnect } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { isTerminal, type Run } from "../src/contracts/index.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";

const home = mkdtempSync(join(tmpdir(), "orbit-cluster-daemon-"));
const bin = join(home, "bin");
mkdirSync(bin);
writeFileSync(
  join(bin, "docker"),
  `#!/bin/sh\ncase "$1" in ps|rm) exit 0;; inspect) echo "Error: No such object: $3" >&2; exit 1;; esac\necho "fake docker: refused $1" >&2\nexit 1\n`,
);
chmodSync(join(bin, "docker"), 0o755);
process.env.PATH = `${bin}:${process.env.PATH}`;

const pPaths = orbitPaths({
  ORBIT_HOME: join(home, "primary"),
  ORBIT_NODE: "p0",
  ORBIT_GPUS: "none",
});
const wPaths = orbitPaths({
  ORBIT_HOME: join(home, "worker"),
  ORBIT_NODE: "w1",
  ORBIT_GPUS: "none",
});
const repo = join(home, "repo");
let primary: StartedDaemon;
let worker: StartedDaemon;
let client: OrbitClient;
let workerUrl: string;

const freePort = () =>
  new Promise<number>((resolve) => {
    const s = createServer().listen(0, "127.0.0.1", () => {
      const port = (s.address() as { port: number }).port;
      s.close(() => resolve(port));
    });
  });

async function until<T>(f: () => Promise<T>, ok: (v: T) => boolean, ms = 15_000): Promise<T> {
  const end = Date.now() + ms;
  for (;;) {
    const v = await f();
    if (ok(v) || Date.now() > end) return v;
    await new Promise((r) => setTimeout(r, 100));
  }
}

beforeAll(async () => {
  mkdirSync(repo);
  const git = (...a: string[]) => execFileSync("git", ["-C", repo, ...a], { stdio: "pipe" });
  git("init", "-q");
  writeFileSync(join(repo, "train.py"), "print('hi')\n");
  git("add", ".");
  git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init");

  const opts = { port: 0, tickMs: 100, heartbeatMs: 200, syncMs: 200 };
  worker = await startDaemon(wPaths, opts);
  primary = await startDaemon(pPaths, opts);
  const c = await tryConnect(pPaths);
  if (!c) throw new Error("primary not reachable");
  client = c;
  const port = await freePort();
  const s = await worker.cluster.setExpose(`127.0.0.1:${port}`);
  expect(s).toMatchObject({ node: "w1", listening: true });
  workerUrl = `http://127.0.0.1:${port}`;
});

afterAll(async () => {
  await primary?.stop();
  await worker?.stop();
  rmSync(home, { recursive: true, force: true });
});

describe("multi-node", () => {
  it("serves the cluster API only with the node token", async () => {
    expect((await fetch(`${workerUrl}/cluster/v1/info`)).status).toBe(401);
    const res = await fetch(`${workerUrl}/cluster/v1/info`, {
      headers: { authorization: `Bearer ${worker.cluster.clusterToken()}` },
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ name: "w1", protocol: 1 });
    // The daemon API token is not a cluster token.
    const other = await fetch(`${workerUrl}/cluster/v1/info`, {
      headers: { authorization: `Bearer ${worker.token}` },
    });
    expect(other.status).toBe(401);
  });

  it("adds a worker by URL and token", async () => {
    await expect(client.nodeAdd(workerUrl, "orbit-node-wrong-token-0000")).rejects.toThrow();
    const n = await client.nodeAdd(workerUrl, worker.cluster.clusterToken());
    expect(n).toMatchObject({ name: "w1", online: true });
    expect(n.info?.resources.gpus).toEqual([]);
    const ledger = await client.ledger();
    expect(ledger.nodes.map((x) => x.name)).toEqual(["w1"]);
  });

  it("rejects runs no node can take, with a reason per node", async () => {
    const base = { command: ["true"], image: "orbit-test/none:1" };
    await expect(client.submit({ ...base, resources: { node: "nowhere" } })).rejects.toThrow(
      /pinned to nowhere/,
    );
    const data = join(home, "data");
    mkdirSync(data);
    await client.datasetPut({ name: "only-here", path: data });
    await expect(
      client.submit({
        ...base,
        resources: { node: "w1" },
        mounts: [{ dataset: "only-here", target: "/d", mode: "ro" }],
      }),
    ).rejects.toThrow(/dataset only-here not registered there/);
  });

  it("sends the code snapshot, places the run on the worker and mirrors its outcome", async () => {
    const r = await client.submit({
      command: ["python", "train.py"],
      image: "orbit-test/none:1",
      project: repo,
      resources: { node: "w1", cpus: 1, memGB: 1 },
    });
    const done = await until(
      () => client.get(r.id),
      (x: Run) => isTerminal(x.state) && x.cleanup !== "pending",
    );
    expect(done).toMatchObject({ remote: true, node: "w1", state: "failed", origin: null });
    expect(done.reason).toMatch(/image|pull|fake docker/);
    expect(done.lease?.state).not.toBe("active");
    const events = (await client.events(r.id)).map((e) => e.kind);
    expect(events).toContain("placed");
    expect(events).toContain("dispatched");

    // The worker holds the same run, marked with its origin, and the code bundle it received.
    const w = worker.runs.get(r.id);
    expect(w).toMatchObject({ origin: "p0", node: "w1", remote: false });
    expect(done.code?.commit).toBeTruthy();
    expect(w?.code?.commit).toBe(done.code?.commit);
    expect(existsSync(join(wPaths.runs, r.id, "workspace", "train.py"))).toBe(true);
  });

  it("forgets a node", async () => {
    await client.nodeRemove("w1");
    expect((await client.nodes()).length).toBe(0);
  });
});
