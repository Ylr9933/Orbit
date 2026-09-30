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
    shim: [process.execPath, fileURLToPath(new URL("../src/bin.ts", import.meta.url))],
  });
  const c = await tryConnect(paths);
  if (!c) throw new Error("daemon not reachable");
  client = c;
  await client.benchmarkPut({ name: "asi", adapter: "asi", path: asi, python: runner });
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
});
