// Explicit terminal-record fixtures; exercises the real store, daemon HTTP API and file deletion.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { BenchmarkRegistry } from "../src/bench/registry.ts";
import { BenchService } from "../src/bench/service.ts";
import { tryConnect } from "../src/client/index.ts";
import { ensureHome, orbitPaths } from "../src/config/paths.ts";
import { BenchJob, Outcome, Run, Trial } from "../src/contracts/index.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";
import { probeNode } from "../src/resources/probe.ts";
import { RunService } from "../src/runs/service.ts";
import { Store } from "../src/store/index.ts";

const homes: string[] = [];
const stores: Store[] = [];
let daemon: StartedDaemon | undefined;
afterEach(async () => {
  await daemon?.stop();
  daemon = undefined;
  for (const s of stores.splice(0)) s.close();
  for (const h of homes.splice(0)) rmSync(h, { recursive: true, force: true });
});
const at = "2026-10-10T00:00:00.000Z";
function fixture() {
  const home = mkdtempSync(join(tmpdir(), "orbit-consolidate-"));
  homes.push(home);
  const paths = orbitPaths({ ORBIT_HOME: home });
  ensureHome(paths);
  const store = new Store(paths.db);
  stores.push(store);
  const runs = new RunService({
    store,
    paths,
    probe: () => probeNode(paths.data, { node: paths.node, gpus: paths.gpus }),
  });
  const bench = new BenchService({
    store,
    paths,
    runs,
    registry: new BenchmarkRegistry(paths.benchmarks),
  });
  const job = (id: string, tasks = ["a"]) => {
    const j = BenchJob.parse({
      id,
      spec: { benchmark: "fixture", tasks, methods: [{ name: "empty", agent: "empty" }] },
      folder: id,
      state: "done",
      createdAt: at,
      endedAt: at,
    });
    store.putJob(j);
    return j;
  };
  const trial = (jobId: string, task: string, valid: boolean) => {
    const id = `${jobId}.${task}`;
    for (const phase of ["solve", "verify"]) {
      const rid = `${id}-${phase}`;
      store.putRun(
        Run.parse({
          id: rid,
          spec: {
            command: ["true"],
            backend: "process",
            group: `bench-${jobId}`,
            tags: { job: jobId, trial: id, phase },
          },
          state: "succeeded",
          reason: null,
          exitCode: 0,
          node: "test",
          image: null,
          containerId: null,
          lease: null,
          code: null,
          cleanup: "done",
          note: "",
          folder: jobId,
          createdAt: at,
          startedAt: at,
          endedAt: at,
        }),
      );
      const output = join(paths.runs, rid, "orbit/output");
      mkdirSync(output, { recursive: true });
      writeFileSync(join(output, "answer"), "retained artifact\n");
    }
    const t = Trial.parse({
      id,
      jobId,
      task,
      method: "empty",
      seed: 1,
      state: "done",
      solveRunId: `${id}-solve`,
      verifyRunId: `${id}-verify`,
      outcome: Outcome.parse({
        execution: "succeeded",
        evaluation: valid ? "valid" : "invalid",
        score: valid ? 0 : null,
        maxScore: 1,
        cleanup: "done",
        issues: valid ? [] : ["fixture build failure"],
      }),
      createdAt: at,
      endedAt: at,
    });
    store.putTrial(t);
    return t;
  };
  job("target", ["a", "b", "c"]);
  trial("target", "a", false);
  trial("target", "b", true);
  trial("target", "c", false);
  job("source");
  trial("source", "a", true);
  return { paths, store, runs, bench, job, trial };
}

it("previews without changes; merges zero scores over HTTP while retaining the target matrix and deleting only invalid artifacts", async () => {
  const f = fixture();
  const original = f.bench.job("target");
  f.store.close();
  stores.splice(stores.indexOf(f.store), 1);
  daemon = await startDaemon(f.paths, { port: 0 });
  const c = await tryConnect(f.paths);
  if (!c) throw new Error("daemon unreachable");
  const plan = await c.benchConsolidate("target", { sources: ["source"], pruneInvalid: true });
  expect(plan.adopted).toEqual([
    { task: "a", sourceJob: "source", sourceTrial: "source.a", trial: "target.a" },
  ]);
  expect(plan.removedRuns.sort()).toEqual([
    "target.a-solve",
    "target.a-verify",
    "target.c-solve",
    "target.c-verify",
  ]);
  expect(await c.benchJob("target")).toEqual(original);
  const applied = await c.benchConsolidate("target", {
    sources: ["source"],
    pruneInvalid: true,
    dryRun: false,
  });
  expect(applied.leftovers).toEqual([]);
  const result = await c.benchJob("target");
  expect(result.trials.map((t) => t.id)).toEqual(original.trials.map((t) => t.id));
  expect(result.summary[0]).toMatchObject({ trials: 3, valid: 2, invalid: 1 });
  expect(result.summary[0]?.metrics.score?.mean).toBe(0);
  expect(result.trials[2]).toMatchObject({
    solveRunId: null,
    verifyRunId: null,
    outcome: { evaluation: "invalid", issues: ["fixture build failure"] },
  });
  await expect(c.benchJob("source")).rejects.toThrow(/not found/);
  const adopted = await c.get("source.a-solve");
  expect(adopted).toMatchObject({
    folder: "target",
    spec: { group: "bench-target", tags: { trial: "target.a", source_trial: "source.a" } },
  });
  expect(readFileSync(join(f.paths.runs, adopted.id, "orbit/output/answer"), "utf8")).toBe(
    "retained artifact\n",
  );
  for (const id of applied.removedRuns) expect(existsSync(join(f.paths.runs, id))).toBe(false);
  await expect(c.deleteRuns([adopted.id])).rejects.toThrow(/belongs to bench job target/);
  expect(
    (await c.benchConsolidate("target", { pruneInvalid: true, dryRun: false })).removedRuns,
  ).toEqual([]);
});

it("rejects duplicate valid results, incompatible jobs and active runs without partial mutation", async () => {
  const f = fixture();
  f.job("second");
  f.trial("second", "a", true);
  const before = f.bench.job("target");
  await expect(
    f.bench.consolidate("target", { sources: ["source", "second"], dryRun: false }),
  ).rejects.toThrow(/replace valid/);
  expect(f.bench.job("target")).toEqual(before);
  const source = f.store.getJob("source");
  if (!source) throw new Error("missing fixture");
  f.store.putJob({ ...source, spec: { ...source.spec, benchmark: "different" } });
  await expect(
    f.bench.consolidate("target", { sources: ["source"], dryRun: false }),
  ).rejects.toThrow(/incompatible/);
  f.store.putJob(source);
  const run = f.runs.get("source.a-solve");
  if (!run) throw new Error("missing fixture run");
  f.store.putRun({ ...run, state: "running" });
  await expect(
    f.bench.consolidate("target", { sources: ["source"], dryRun: false }),
  ).rejects.toThrow(/running/);
  expect(f.bench.job("target")).toEqual(before);
});

it("prunes invalid scoring history but preserves valid histories and effective zero scores", async () => {
  const f = fixture();
  const old = f.store.getTrial("target.b");
  const bad = f.store.getTrial("target.c");
  if (!old?.outcome || !bad?.outcome) throw new Error("missing fixture");
  // Explicit invalid verifier fixture attached to an otherwise valid trial.
  const rid = "old-invalid-verifier";
  const run = f.runs.get("target.c-verify");
  if (!run) throw new Error("missing fixture run");
  f.store.putRun({ ...run, id: rid });
  f.store.putTrial({
    ...old,
    history: [
      { verifyRunId: rid, outcome: bad.outcome, endedAt: at },
      { verifyRunId: null, outcome: old.outcome, endedAt: at },
    ],
  });
  const out = await f.bench.consolidate("target", { pruneInvalid: true, dryRun: false });
  expect(out.removedRuns).toContain(rid);
  expect(out.removedRuns).not.toContain("target.b-solve");
  expect(f.store.getTrial(old.id)?.history).toHaveLength(1);
});
