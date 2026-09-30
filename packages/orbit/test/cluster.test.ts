// Multi-node building blocks without daemons: bundle hashing and transfer, placement rules, node
// configuration parsing and the dataset registry.
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { parseDataset } from "../src/cli/cluster.ts";
import { parseListen } from "../src/cluster/registry.ts";
import { tokenMatches } from "../src/cluster/worker.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type Lease, type NodeResources, type Run, RunSpec } from "../src/contracts/index.ts";
import { filterGpus } from "../src/resources/probe.ts";
import { joinReasons, nodeLeases, type RemoteNode, remoteBlocker } from "../src/runs/placement.ts";
import { packBundle, receiveBundle, treeHash } from "../src/workspace/bundle.ts";
import { DatasetRegistry } from "../src/workspace/datasets.ts";

const tmp = mkdtempSync(join(tmpdir(), "orbit-cluster-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

function tree(name: string): string {
  const d = join(tmp, name);
  mkdirSync(join(d, "src"), { recursive: true });
  writeFileSync(join(d, "a.txt"), "hello\n");
  writeFileSync(join(d, "src", "run.sh"), "#!/bin/sh\necho hi\n");
  chmodSync(join(d, "src", "run.sh"), 0o755);
  symlinkSync("src/run.sh", join(d, "link"));
  return d;
}

describe("bundles", () => {
  it("hashes content, modes and links, not location", async () => {
    const a = tree("a");
    const b = tree("b");
    const h = await treeHash(a);
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(await treeHash(b)).toBe(h);
    chmodSync(join(b, "src", "run.sh"), 0o644);
    expect(await treeHash(b)).not.toBe(h);
    chmodSync(join(b, "src", "run.sh"), 0o755);
    writeFileSync(join(b, "a.txt"), "hello!\n");
    expect(await treeHash(b)).not.toBe(h);
    await expect(treeHash(a, 4)).rejects.toThrow(/exceeds/);
  });

  it("round-trips through tar and refuses content that does not match its hash", async () => {
    const src = tree("c");
    const h = await treeHash(src);
    const root = join(tmp, "cache");
    const dest = await receiveBundle(root, h, packBundle(src));
    expect(dest).toBe(join(root, h));
    expect(readFileSync(join(dest, "a.txt"), "utf8")).toBe("hello\n");
    expect(statSync(join(dest, "src", "run.sh")).mode & 0o100).toBeTruthy();
    // Idempotent: a second upload of the same bundle keeps the first.
    expect(await receiveBundle(root, h, packBundle(src))).toBe(dest);

    const wrong = "0".repeat(64);
    await expect(receiveBundle(root, wrong, packBundle(src))).rejects.toThrow(/mismatch/);
    expect(existsSync(join(root, wrong))).toBe(false);
    await expect(receiveBundle(root, "../x", packBundle(src))).rejects.toThrow(/bad bundle/);
  });
});

const gpu = (index: number, memGiB = 24) => ({
  index,
  uuid: `GPU-${index}`,
  name: "Test GPU",
  memTotalMiB: memGiB * 1024,
  memUsedMiB: 0,
  utilPct: 0,
  externalMemMiB: 0,
  available: true,
});

const resources = (n: number): NodeResources => ({
  node: "w1",
  probedAt: "2026-09-30T00:00:00Z",
  gpus: Array.from({ length: n }, (_, i) => gpu(i)),
  gpuError: null,
  cpu: { count: 16, load1: 0 },
  memory: { totalGB: 64, availableGB: 60 },
  disk: { path: "/", totalGB: 100, freeGB: 50 },
});

const worker = (over: Partial<RemoteNode> = {}): RemoteNode => ({
  name: "w1",
  online: true,
  resources: resources(4),
  leases: [],
  datasets: ["imagenet"],
  profiles: [{ name: "codex", harness: "codex", cli: true }],
  ...over,
});

const spec = (over: Record<string, unknown> = {}) =>
  RunSpec.parse({ command: ["true"], image: "python:3.12-slim", ...over });

describe("remote placement", () => {
  it("accepts a self-contained docker run and explains every rejection", () => {
    expect(remoteBlocker(spec({ resources: { gpus: 2 } }), worker())).toBeNull();
    expect(remoteBlocker(spec({ resources: { node: "w2" } }), worker())).toBe("pinned to w2");
    expect(remoteBlocker(spec(), worker({ resources: null }))).toBe("not reachable yet");
    expect(remoteBlocker(spec({ backend: "process", image: undefined }), worker())).toMatch(
      /process runs/,
    );
    expect(
      remoteBlocker(spec({ mounts: [{ source: "/data/x", target: "/x" }] }), worker()),
    ).toMatch(/host path mount \/data\/x/);
    expect(remoteBlocker(spec({ project: "/repo", snapshot: false }), worker())).toMatch(
      /without snapshot/,
    );
    expect(
      remoteBlocker(
        spec({
          mounts: [
            { dataset: "imagenet", target: "/d" },
            { dataset: "coco", target: "/c" },
          ],
        }),
        worker(),
      ),
    ).toBe("dataset coco not registered there");
    expect(remoteBlocker(spec({ auth: "claude" }), worker())).toMatch(/not configured there/);
    expect(
      remoteBlocker(
        spec({ auth: "codex" }),
        worker({ profiles: [{ name: "codex", harness: "codex", cli: false }] }),
      ),
    ).toBe("codex CLI not installed there");
    expect(remoteBlocker(spec({ resources: { gpus: 8 } }), worker())).toMatch(/needs 8 GPU/);
  });

  it("requires exactly one of source and dataset in a mount", () => {
    expect(() => spec({ mounts: [{ target: "/x" }] })).toThrow();
    expect(() => spec({ mounts: [{ source: "/a", dataset: "b", target: "/x" }] })).toThrow();
  });

  it("counts predicted leases of runs the node has not reported yet", () => {
    const lease = (runId: string): Lease => ({
      id: `l-${runId}`,
      runId,
      node: "w1",
      gpuIds: ["GPU-0"],
      cpus: 1,
      memGB: 1,
      state: "active",
      createdAt: "2026-09-30T00:00:00Z",
      releasedAt: null,
    });
    const mirror = (id: string, node = "w1") => ({ id, node, lease: lease(id) }) as unknown as Run;
    const n = worker({ leases: [lease("a")] });
    expect(
      nodeLeases(n, [mirror("a"), mirror("b"), mirror("c", "w2")]).map((l) => l.runId),
    ).toEqual(["a", "b"]);
  });

  it("joins reasons per node", () => {
    expect(joinReasons([["w1", "busy"]])).toBe("busy");
    expect(
      joinReasons([
        ["local", "busy"],
        ["w1", "offline"],
      ]),
    ).toBe("local: busy; w1: offline");
  });
});

describe("node configuration", () => {
  it("reads the node name and GPU subset from the environment", () => {
    const p = orbitPaths({ ORBIT_HOME: tmp, ORBIT_NODE: "gpu-a", ORBIT_GPUS: " 0, 2 ," });
    expect(p.node).toBe("gpu-a");
    expect(p.gpus).toEqual(["0", "2"]);
    expect(orbitPaths({ ORBIT_HOME: tmp }).gpus).toBeNull();
    const gs = [gpu(0), gpu(1), gpu(2)];
    expect(filterGpus(gs, ["0", "GPU-2"]).map((g) => g.index)).toEqual([0, 2]);
    expect(filterGpus(gs, null)).toHaveLength(3);
  });

  it("parses listen addresses and dataset flags", () => {
    expect(parseListen("100.64.0.2:7718")).toEqual({ host: "100.64.0.2", port: 7718 });
    expect(parseListen("[::1]:80")).toEqual({ host: "::1", port: 80 });
    expect(() => parseListen("7718")).toThrow(/HOST:PORT/);
    expect(() => parseListen("h:70000")).toThrow();
    expect(parseDataset("imagenet")).toEqual({
      dataset: "imagenet",
      target: "/data/imagenet",
      mode: "ro",
    });
    expect(parseDataset("w:/models/w:rw")).toEqual({
      dataset: "w",
      target: "/models/w",
      mode: "rw",
    });
    expect(() => parseDataset("a:b:x")).toThrow();
  });

  it("checks the bearer token", () => {
    expect(tokenMatches("Bearer orbit-node-abc", "orbit-node-abc")).toBe(true);
    expect(tokenMatches("Bearer orbit-node-abd", "orbit-node-abc")).toBe(false);
    expect(tokenMatches("orbit-node-abc", "orbit-node-abc")).toBe(false);
    expect(tokenMatches(undefined, "orbit-node-abc")).toBe(false);
  });

  it("registers datasets by name with a private file", () => {
    const file = join(tmp, "datasets.json");
    const reg = new DatasetRegistry(file);
    const dir = join(tmp, "data");
    mkdirSync(dir);
    expect(reg.put({ name: "d1", path: dir }).path).toBe(dir);
    expect(reg.path("d1")).toBe(dir);
    expect(statSync(file).mode & 0o777).toBe(0o600);
    expect(() => reg.put({ name: "d2", path: join(tmp, "missing") })).toThrow(/not found/);
    expect(() => reg.put({ name: "d3", path: "relative" })).toThrow();
    expect(reg.remove("d1")).toBe(true);
    expect(reg.list()).toEqual([]);
  });
});
