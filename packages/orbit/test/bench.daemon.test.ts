// A benchmark job end to end through the daemon: process-backend solve and verify runs, scoring and
// aggregation. The "python" of the ASI benchmark is a fake runner, so no Docker or model is needed.
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { type OrbitClient, tryConnect } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";
import { probeNode } from "../src/resources/probe.ts";

const home = mkdtempSync(join(tmpdir(), "orbit-bench-daemon-"));
const paths = orbitPaths({ ORBIT_HOME: join(home, "orbit") });
const asi = join(home, "asi");
let daemon: StartedDaemon;
let client: OrbitClient;

// `python -m ai4sci_bench.cli run|score ...`: `run` records whether a real agent command was given,
// `score` gives 100 to the oracle's results and 0 otherwise.
const FAKE_RUNNER = `#!${process.execPath}
const fs = require("node:fs"), path = require("node:path");
const a = process.argv.slice(2);
const get = (f) => a[a.indexOf(f) + 1];
if (a[2] === "run") {
  const task = get("--tasks"), level = get("--prompt-levels"), out = get("--output-dir");
  const oracle = (get("--agent-cmd") ?? "").includes("/reference");
  fs.mkdirSync(path.join(out, task), { recursive: true });
  const inst = task + "__seed31415";
  fs.writeFileSync(path.join(out, task, inst + "__" + level + ".json"),
    JSON.stringify({ instance_id: inst, prompt_level: level, status: "completed", oracle }));
} else if (a[2] === "score") {
  const dir = get("--results-dir"), results = [];
  for (const t of fs.readdirSync(dir))
    for (const f of fs.readdirSync(path.join(dir, t)).filter((f) => f.endsWith(".json"))) {
      const r = JSON.parse(fs.readFileSync(path.join(dir, t, f), "utf8"));
      results.push({ instance_id: r.instance_id, prompt_level: r.prompt_level, attempt: 1,
        final_score: r.oracle ? 100 : 0, max_score: 100 });
    }
  fs.writeFileSync(get("--output"), JSON.stringify({ results }));
} else process.exit(2);
`;

// An external adapter: process runs; the oracle writes the answer, the verifier copies it to a score.
const EXTERNAL_ADAPTER = `#!${process.execPath}
let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  const req = JSON.parse(input);
  const say = (v) => console.log(JSON.stringify(v));
  if (req.benchmark.config.broken) { console.error("checkout has no tasks/"); process.exit(1); }
  if (req.op === "tasks") return say({ tasks: [{ id: "t1", title: "one", supported: true, reason: null }] });
  const node = ${JSON.stringify(process.execPath)};
  if (req.op === "solve") {
    const v = req.trial.method.agent === "oracle" ? "7" : "0";
    return say({ spec: { backend: "process", resources: { cpus: 1, memGB: 1 }, command: ["sh", "-c", "sleep 0.5; echo " + v + " > $ORBIT_OUTPUT/answer"] } });
  }
  if (req.op === "verify")
    return say({ spec: { backend: "process", command: ["sh", "-c", "cp " + req.solve.output + "/answer $ORBIT_OUTPUT/score"] } });
  const fs = require("node:fs");
  say({ score: Number(fs.readFileSync(req.verify.output + "/score", "utf8")), maxScore: 7 });
});
`;

beforeAll(async () => {
  for (const [task, status] of [
    ["math.a", "final"],
    ["math.b", "final"],
    ["math.draft", "draft"],
  ] as const) {
    const t = join(asi, "tasks", "math", task.slice(5));
    mkdirSync(t, { recursive: true });
    writeFileSync(
      join(t, "task_meta.yaml"),
      `id: ${task}\nstatus: ${status}\ndomain: math\noutput:\n  files:\n    - name: out.txt\n`,
    );
    mkdirSync(join(asi, "bench_runs", "instances_seed31415", `${task}__seed31415`, "reference"), {
      recursive: true,
    });
  }
  const runner = join(home, "fake-python");
  writeFileSync(runner, FAKE_RUNNER);
  chmodSync(runner, 0o755);
  daemon = await startDaemon(paths, {
    port: 0,
    tickMs: 100,
    usageMs: 200,
    self: [process.execPath, fileURLToPath(new URL("../src/bin.ts", import.meta.url))],
    // ASI solve runs lease 8 GB; small CI runners have less, and these runs are tiny fake runners.
    probe: async () => ({
      ...(await probeNode(paths.home, { node: paths.node, gpus: paths.gpus })),
      cpu: { count: 16, load1: 0, busy: 0 },
      memory: { totalGB: 64, availableGB: 64 },
    }),
  });
  const c = await tryConnect(paths);
  if (!c) throw new Error("daemon not reachable");
  client = c;
  await client.benchmarkPut({ name: "asi", adapter: "asi", path: asi, config: { python: runner } });
  const external = join(home, "adapter.cjs");
  writeFileSync(external, EXTERNAL_ADAPTER);
  chmodSync(external, 0o755);
  await client.benchmarkPut({ name: "ext", adapter: external, path: home });
});
afterAll(async () => {
  // Let run cleanup finish before the home directory goes away.
  for (let i = 0; i < 50; i++) {
    const runs = client ? await client.list({ limit: 1000 }) : [];
    if (runs.every((r) => r.cleanup !== "pending")) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  await daemon?.stop();
  rmSync(home, { recursive: true, force: true });
});

describe("bench jobs", () => {
  it("lists tasks and rejects unsupported ones and bad methods", async () => {
    const tasks = await client.benchTasks("asi");
    expect(tasks.map((t) => [t.id, t.supported])).toEqual([
      ["math.a", true],
      ["math.b", true],
      ["math.draft", false],
    ]);
    await expect(
      client.benchSubmit({
        benchmark: "asi",
        tasks: ["math.draft"],
        methods: [{ name: "oracle", agent: "oracle" }],
      }),
    ).rejects.toThrow(/not supported/);
    await expect(
      client.benchSubmit({
        benchmark: "asi",
        methods: [{ name: "c", agent: "codex", auth: "nope" }],
      }),
    ).rejects.toThrow(/auth profile not found/);
  });

  it("runs oracle and empty as separate solve and verify runs and aggregates valid scores", async () => {
    const job = await client.benchSubmit({
      name: "smoke",
      benchmark: "asi",
      methods: [
        { name: "oracle", agent: "oracle" },
        { name: "empty", agent: "empty" },
      ],
    });
    let d = await client.benchJob(job.id);
    for (let i = 0; i < 300 && d.job.state === "running"; i++) {
      await new Promise((r) => setTimeout(r, 100));
      d = await client.benchJob(job.id);
    }
    expect(d.job.state).toBe("done");
    expect(d.trials).toHaveLength(4);
    for (const t of d.trials) {
      expect(t.outcome?.evaluation, JSON.stringify(t.outcome)).toBe("valid");
      expect(t.solveRunId).not.toBe(t.verifyRunId);
    }
    expect(d.summary.map((s) => [s.method, s.meanPct, s.valid])).toEqual([
      ["oracle", 100, 2],
      ["empty", 0, 2],
    ]);
    const verify = await client.get(d.trials[0]?.verifyRunId ?? "");
    expect(verify.spec.priority).toBe(1);
    expect(verify.spec.tags).toMatchObject({ bench: "asi", job: job.id, phase: "verify" });
    // Staging copies are removed when trials finish.
    expect(
      existsSync(join(paths.bench, job.id)) ? readdirSync(join(paths.bench, job.id)) : [],
    ).toEqual([]);

    const c = await client.benchCompare([job.id]);
    expect(c.means).toEqual({ oracle: { all: 100, paired: 100 }, empty: { all: 0, paired: 0 } });
    expect((await client.benchJobs()).map((j) => j.id)).toContain(job.id);
  });

  it("runs an external adapter and refuses to register one that fails", async () => {
    const adapter = join(home, "adapter.cjs");
    await expect(
      client.benchmarkPut({ name: "bad", adapter, path: home, config: { broken: "1" } }),
    ).rejects.toThrow(/adapter tasks: exit 1: checkout has no tasks/);
    await expect(client.benchmarkPut({ name: "bad", adapter: home, path: home })).rejects.toThrow(
      /not an executable file/,
    );
    expect((await client.benchmarks()).map((b) => b.name)).toEqual(["asi", "ext"]);

    const job = await client.benchSubmit({
      benchmark: "ext",
      methods: [
        { name: "oracle", agent: "oracle" },
        { name: "empty", agent: "empty" },
      ],
    });
    let d = await client.benchJob(job.id);
    for (let i = 0; i < 300 && d.job.state === "running"; i++) {
      await new Promise((r) => setTimeout(r, 100));
      d = await client.benchJob(job.id);
    }
    expect(d.job.state).toBe("done");
    expect(d.trials.map((t) => [t.method, t.outcome?.evaluation, t.outcome?.score])).toEqual([
      ["oracle", "valid", 7],
      ["empty", "valid", 0],
    ]);
    expect(d.summary.map((s) => [s.method, s.meanPct])).toEqual([
      ["oracle", 100],
      ["empty", 0],
    ]);
  });

  it("applies a resources file to solve runs, records usage and suggests from it", async () => {
    const adapter = join(home, "adapter.cjs");
    const res = join(home, "resources.json");
    writeFileSync(res, JSON.stringify({ version: 1, tasks: { nope: { memGB: 2 } } }));
    await expect(
      client.benchmarkPut({ name: "res", adapter, path: home, resources: res }),
    ).rejects.toThrow(/unknown tasks: nope/);
    writeFileSync(
      res,
      JSON.stringify({
        version: 1,
        default: { cpus: 2, memGB: 3, timeoutMin: 5 },
        tasks: { t1: { memGB: 4, evidence: "measured", confidence: "high" } },
      }),
    );
    await client.benchmarkPut({ name: "res", adapter, path: home, resources: res });
    const job = await client.benchSubmit({
      benchmark: "res",
      methods: [{ name: "oracle", agent: "oracle" }],
    });
    expect(job.resources).toEqual({ t1: { cpus: 2, memGB: 4, timeoutMin: 5 } });
    let d = await client.benchJob(job.id);
    for (let i = 0; i < 300 && d.job.state === "running"; i++) {
      await new Promise((r) => setTimeout(r, 100));
      d = await client.benchJob(job.id);
    }
    const solve = await client.get(d.trials[0]?.solveRunId ?? "");
    expect(solve.spec.resources).toMatchObject({ cpus: 2, memGB: 4 });
    expect(solve.spec.timeoutMin).toBe(5);
    expect(solve.usage?.peakMemGB).toBeGreaterThan(0);
    // The verify run keeps the adapter's own resources.
    const verify = await client.get(d.trials[0]?.verifyRunId ?? "");
    expect(verify.spec.resources.memGB).not.toBe(4);
    // Oracle runs say nothing about what a task needs: they are left out of the suggestions.
    expect((await client.benchUsage([job.id])).rows).toEqual([]);
  });
});
