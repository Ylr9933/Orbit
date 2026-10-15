// Real store and adapter planning with explicit submission/scoring fakes; no runs are executed.
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdapterClient } from "../src/bench/protocol.ts";
import { BenchmarkRegistry } from "../src/bench/registry.ts";
import { BenchService } from "../src/bench/service.ts";
import { ensureHome, orbitPaths } from "../src/config/paths.ts";
import { BenchJob, Run, Trial } from "../src/contracts/index.ts";
import { RunService } from "../src/runs/service.ts";
import { Store } from "../src/store/index.ts";

const homes: string[] = [];
const stores: Store[] = [];
const at = "2026-10-16T00:00:00.000Z";
const task = "math.example";
afterEach(() => {
  vi.restoreAllMocks();
  for (const store of stores.splice(0)) store.close();
  for (const home of homes.splice(0)) rmSync(home, { recursive: true, force: true });
});

const write = (file: string, text: string) => {
  mkdirSync(join(file, ".."), { recursive: true });
  writeFileSync(file, text);
};

function fixture(adapter = "harbor") {
  const home = mkdtempSync(join(tmpdir(), "orbit-bench-service-"));
  homes.push(home);
  const paths = orbitPaths({ ORBIT_HOME: home });
  ensureHome(paths);
  const store = new Store(paths.db);
  stores.push(store);
  const runs = new RunService({ store, paths, probe: vi.fn() });
  const registry = new BenchmarkRegistry(paths.benchmarks);
  const source = join(home, "checkout");
  mkdirSync(source);
  registry.put({ name: "fixture", path: source, adapter });
  const bench = new BenchService({
    store,
    paths,
    runs,
    registry,
    self: [process.execPath, fileURLToPath(new URL("../src/bin.ts", import.meta.url))],
  });
  const run = Run.parse({
    id: "solve",
    spec: { command: ["true"], backend: "process" },
    state: "succeeded",
    reason: null,
    exitCode: 0,
    node: "fixture",
    image: null,
    containerId: null,
    lease: null,
    code: null,
    cleanup: "done",
    note: "",
    createdAt: at,
    startedAt: at,
    endedAt: at,
  });
  const job = BenchJob.parse({
    id: "job",
    spec: { benchmark: "fixture", tasks: [task], methods: [{ name: "empty", agent: "empty" }] },
    state: "running",
    createdAt: at,
    endedAt: null,
  });
  const trial = Trial.parse({
    id: "job.1",
    jobId: job.id,
    task,
    method: "empty",
    seed: 1,
    state: "pending",
    solveRunId: null,
    verifyRunId: null,
    outcome: null,
    createdAt: at,
    endedAt: null,
  });
  const submit = vi.spyOn(runs, "submit").mockImplementation(async (spec) => {
    const queued = Run.parse({ ...run, id: "submitted", spec, state: "queued", startedAt: null });
    store.putRun(queued);
    return queued;
  });
  return { home, paths, source, store, runs, registry, bench, run, job, trial, submit };
}

describe.each(["asi", "harbor", "external"])("%s effective solve timeout", (adapter) => {
  it.each([
    { label: "adapter default", cli: undefined, defaults: undefined, taskTimeout: undefined },
    { label: "resources default", cli: undefined, defaults: 9, taskTimeout: undefined },
    { label: "task over default", cli: undefined, defaults: 9, taskTimeout: 6 },
    { label: "CLI over task", cli: 3, defaults: 9, taskTimeout: 6 },
    { label: "CLI without resources", cli: 3, defaults: undefined, taskTimeout: undefined },
  ])("resolves $label before adapter planning", async ({ cli, defaults, taskTimeout }) => {
    const f = fixture(adapter === "external" ? "harbor" : adapter);
    write(join(f.source, "tasks/math/example/task_meta.yaml"), `id: ${task}\nstatus: final\n`);
    mkdirSync(join(f.source, "bench_runs/instances_seed31415", `${task}__seed31415/reference`), {
      recursive: true,
    });
    write(
      join(f.source, "tasks", task, "task.toml"),
      `[environment]
docker_image = "fixture"
[agent]
timeout_sec = 600
[verifier]
environment_mode = "separate"
timeout_sec = 120
`,
    );
    write(join(f.source, "tasks", task, "instruction.md"), "Fixture instruction\n");
    write(join(f.source, "tasks", task, "tests/test.sh"), "#!/bin/sh\nexit 0\n");
    let executable = adapter;
    if (adapter === "external") {
      executable = join(f.home, "adapter.cjs");
      write(
        executable,
        `#!${process.execPath}
let input = "";
process.stdin.on("data", c => input += c);
process.stdin.on("end", () => {
  const req = JSON.parse(input);
  console.log(JSON.stringify(req.op === "tasks" ? { tasks: [{ id: "${task}", title: null, supported: true, reason: null }] } : {
    spec: { backend: "process", command: ["echo", String(req.trial.timeoutMin ?? "adapter")], timeoutMin: 17 }
  }));
});
`,
      );
      chmodSync(executable, 0o755);
    }
    const resources = join(f.home, "resources.json");
    write(
      resources,
      JSON.stringify({
        version: 1,
        default: { timeoutMin: defaults },
        tasks: { [task]: { timeoutMin: taskTimeout } },
      }),
    );
    f.registry.put({ name: "fixture", path: f.source, adapter: executable, resources });
    const job = await f.bench.submit({
      benchmark: "fixture",
      methods: [{ name: "empty", agent: "empty" }],
      timeoutMin: cli,
    });
    await expect.poll(() => f.store.trials(job.id)[0]?.state).toBe("solving");
    const spec = f.submit.mock.calls[0]?.[0];
    const effective = cli ?? taskTimeout ?? defaults;
    expect(spec?.timeoutMin).toBe(
      effective ?? (adapter === "harbor" ? 10 : adapter === "external" ? 17 : undefined),
    );
    if (adapter === "asi") {
      if (effective === undefined) expect(spec?.command).not.toContain("--timeout");
      else {
        const index = spec?.command?.indexOf("--timeout") ?? -1;
        expect(index).toBeGreaterThan(-1);
        expect(spec?.command?.[index + 1]).toBe(String(effective * 60));
      }
    } else if (adapter === "external") {
      expect(spec?.command).toEqual(["echo", String(effective ?? "adapter")]);
    }
  });
});

const agentIssue = "Agent stopped: model_unreachable (workspace routing discovery failed)";
function agentSession(f: ReturnType<typeof fixture>, recovered = false) {
  const turn = (error: unknown) =>
    JSON.stringify({ type: "event_msg", payload: { type: "task_complete", error } });
  write(
    join(f.runs.dirs(f.run.id).agent, "codex/sessions/2026/10/16/rollout-fixture.jsonl"),
    `${turn({ message: "workspace routing discovery failed" })}\n${recovered ? `${turn(null)}\n` : ""}`,
  );
}

it.each(["failed", "succeeded"] as const)(
  "skips verification for an Agent failure even when the solve %s",
  async (state) => {
    const f = fixture();
    f.store.putJob(f.job);
    f.store.putTrial({ ...f.trial, state: "solving", solveRunId: f.run.id });
    f.store.putRun({ ...f.run, state });
    agentSession(f);
    f.bench.start();
    await expect.poll(() => f.store.getTrial(f.trial.id)?.state).toBe("done");
    expect(f.submit).not.toHaveBeenCalled();
    expect(f.store.getTrial(f.trial.id)?.outcome).toMatchObject({
      evaluation: "invalid",
      score: null,
      issues: [agentIssue, "verify skipped"],
    });
  },
);

it("verifies a recovered last turn and keeps the verifier's own timeout", async () => {
  const f = fixture();
  f.store.putJob({ ...f.job, resources: { [task]: { timeoutMin: 3 } } });
  f.store.putTrial({ ...f.trial, state: "solving", solveRunId: f.run.id });
  f.store.putRun(f.run);
  agentSession(f, true);
  vi.spyOn(AdapterClient.prototype, "verify").mockResolvedValue({
    spec: { backend: "process", command: ["true"], timeoutMin: 7 },
    issues: [],
  });
  f.bench.start();
  await expect.poll(() => f.store.getTrial(f.trial.id)?.state).toBe("verifying");
  expect(f.submit.mock.calls[0]?.[0].timeoutMin).toBe(7);
});

it.each([false, true])("scores an Agent failure with an after phase: %s", async (inline) => {
  const f = fixture();
  const solve = Run.parse({
    ...f.run,
    spec: {
      ...f.run.spec,
      ...(inline
        ? { backend: "docker", image: "fixture", after: { command: ["true"], timeoutMin: 1 } }
        : {}),
    },
    ...(inline
      ? { after: { state: "succeeded", exitCode: 0, reason: null, startedAt: at, endedAt: at } }
      : {}),
  });
  f.store.putJob(f.job);
  f.store.putRun(solve);
  f.store.putRun({ ...f.run, id: "verify" });
  f.store.putTrial({
    ...f.trial,
    state: inline ? "solving" : "verifying",
    solveRunId: solve.id,
    verifyRunId: inline ? null : "verify",
  });
  agentSession(f);
  vi.spyOn(AdapterClient.prototype, "score").mockResolvedValue({
    score: 0.5,
    maxScore: 1,
    invalid: false,
    issues: [],
  });
  f.bench.start();
  await expect.poll(() => f.store.getTrial(f.trial.id)?.state).toBe("done");
  expect(f.store.getTrial(f.trial.id)?.outcome).toMatchObject({
    evaluation: inline ? "valid" : "invalid",
    score: 0.5,
    issues: inline ? [] : [agentIssue],
  });
});
