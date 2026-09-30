import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { agentCommand } from "../src/bench/adapter.ts";
import { asiScore, modelError, oracleTemplate, parseTaskMeta } from "../src/bench/asi.ts";
import { classify, solveVerdict } from "../src/bench/classify.ts";
import {
  findHarborTasks,
  harborReward,
  harborSolveSpec,
  harborVerifySpec,
  parseArtifacts,
} from "../src/bench/harbor.ts";
import { compareJobs, summarize } from "../src/bench/service.ts";
import { parseMethod } from "../src/cli/bench.ts";
import type { BenchJob, Benchmark, Run, Trial } from "../src/contracts/index.ts";
import { rewriteDockerArgs, type ShimConfig } from "../src/runs/shim.ts";

const tmp = mkdtempSync(join(tmpdir(), "orbit-bench-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

const write = (file: string, text: string) => {
  mkdirSync(join(file, ".."), { recursive: true });
  writeFileSync(file, text);
};

describe("docker shim", () => {
  const cfg: ShimConfig = {
    realDocker: "/usr/bin/docker",
    dockerConfig: "/h/.docker",
    runId: "r1",
    homeLabel: "abc",
    gpuIds: ["GPU-1"],
    gpuMode: "gpus",
    hostNetwork: true,
    auth: null,
  };

  it("labels containers, maps --gpus to the lease and keeps the command intact", () => {
    const out = rewriteDockerArgs(
      ["run", "--rm", "-v", "/a:/b", "--gpus", "all", "img", "--gpus", "x"],
      cfg,
    );
    expect(out.slice(0, 5)).toEqual([
      "run",
      "--label",
      "orbit.parent=r1",
      "--label",
      "orbit.home=abc",
    ]);
    expect(out).toContain('"device=GPU-1"');
    expect(out).not.toContain("all");
    // Arguments after the image belong to the container command.
    expect(out.slice(-3)).toEqual(["img", "--gpus", "x"]);
  });

  it("refuses GPUs without a lease, adds host network to builds, passes other commands", () => {
    expect(() => rewriteDockerArgs(["run", "--gpus=all", "img"], { ...cfg, gpuIds: [] })).toThrow(
      /leased no GPUs/,
    );
    expect(rewriteDockerArgs(["build", "-t", "x", "."], cfg)).toEqual([
      "build",
      "--network",
      "host",
      "-t",
      "x",
      ".",
    ]);
    expect(rewriteDockerArgs(["ps", "-a"], cfg)).toEqual(["ps", "-a"]);
  });

  it("injects the Agent CLI, credentials and PATH when the run has auth", () => {
    const out = rewriteDockerArgs(
      ["run", "img", "sh"],
      {
        ...cfg,
        auth: {
          mounts: [{ source: "/cli", target: "/orbit/cli", mode: "ro" }],
          agentDir: "/run/agent",
          env: { CODEX_HOME: "/orbit/agent/codex" },
          envFile: "/run/env",
          pathDirs: ["/orbit/cli/bin"],
        },
      },
      () => "/usr/bin:/bin",
    );
    expect(out).toContain("/cli:/orbit/cli:ro");
    expect(out).toContain("CODEX_HOME=/orbit/agent/codex");
    expect(out).toContain("/run/env");
    expect(out.find((a) => a.startsWith("PATH="))).toMatch(
      /^PATH=\/orbit\/cli\/bin.*\/usr\/bin:\/bin$/,
    );
  });
});

describe("harbor adapter", () => {
  const root = join(tmp, "tbs");
  const task = (name: string, toml: string, files: string[] = []) => {
    const d = join(root, "tasks", name);
    write(join(d, "task.toml"), toml);
    for (const f of ["instruction.md", "environment/Dockerfile", "tests/Dockerfile", ...files])
      write(join(d, f), "x\n");
    return d;
  };
  task(
    "sr",
    `artifacts = ["/app/out/"]
[task]
name = "symbolic regression"
[metadata]
domain = "physics"
[agent]
timeout_sec = 600
[environment]
cpus = 4
memory_mb = 8192
network_mode = "no-network"
[verifier]
environment_mode = "separate"
timeout_sec = 120
[solution.env]
SEED = 1
`,
    ["solution/solve.sh"],
  );
  task("shared", `[verifier]\nenvironment_mode = "shared"\n`);
  task("compose", `[verifier]\nenvironment_mode = "separate"\n`, [
    "environment/docker-compose.yaml",
  ]);
  write(join(root, "tasks", "broken", "task.toml"), "not = [toml");

  it("parses artifacts: strings, tables, and skips placeholders and other services", () => {
    const r = parseArtifacts([
      "/a/",
      { source: "/b", destination: "/c" },
      { source: "/d", exclude: ["*"] },
      { source: "/e", service: "db" },
    ]);
    expect(r.artifacts).toEqual([
      { source: "/a", destination: "/a" },
      { source: "/b", destination: "/c" },
    ]);
    expect(r.skipped).toEqual(["/d", "/e"]);
  });

  it("lists tasks and explains the unsupported ones", () => {
    const ts = findHarborTasks(root);
    const by = Object.fromEntries(ts.map((t) => [t.id, t]));
    expect(Object.keys(by).sort()).toEqual(["broken", "compose", "shared", "sr"]);
    expect(by.sr?.supported).toBe(true);
    expect(by.sr?.env).toMatchObject({ cpus: 4, memGB: 8, network: false });
    expect(by.sr?.tags).toEqual({ domain: "physics" });
    expect(by.shared?.reason).toMatch(/environment_mode "shared"/);
    expect(by.compose?.reason).toMatch(/docker-compose/);
    expect(by.broken?.reason).toMatch(/^task.toml:/);
  });

  it("builds oracle, empty and agent solve runs, and a verify run with copied artifacts", () => {
    const t = findHarborTasks(root).find((x) => x.id === "sr");
    if (!t) throw new Error("task missing");
    const staging = join(tmp, "staging");
    const oracle = harborSolveSpec(t, { name: "oracle", agent: "oracle" }, staging);
    expect(oracle.command).toEqual(["bash", "/solution/solve.sh"]);
    expect(oracle.env).toMatchObject({ SEED: "1" });
    expect(oracle.collect).toEqual(["/app/out"]);
    expect(oracle.network).toBe(false);
    expect(oracle.timeoutMin).toBe(10);
    const empty = harborSolveSpec(t, { name: "empty", agent: "empty" }, staging);
    expect(empty.command).toEqual(["true"]);
    const agent = harborSolveSpec(
      t,
      { name: "c", agent: "codex", auth: "p", model: "m", effort: "high" },
      staging,
      5,
    );
    expect(agent.command?.slice(0, 2)).toEqual(["codex", "exec"]);
    expect(agent.network).toBe(true);
    expect(agent.timeoutMin).toBe(5);

    const solveOut = join(tmp, "solve-out");
    const plan0 = harborVerifySpec(t, solveOut, staging);
    expect(plan0.missing).toEqual(["/app/out"]);
    write(join(solveOut, "collected", "app", "out", "result.txt"), "42\n");
    const plan = harborVerifySpec(t, solveOut, staging);
    expect(plan.missing).toEqual([]);
    expect(plan.spec.priority).toBe(1);
    expect(plan.spec.timeoutMin).toBe(2);
    expect(plan.spec.collect).toEqual(["/logs/verifier"]);
    expect(JSON.stringify(plan.spec.mounts)).toContain("/app/out");
  });

  it("reads rewards from reward.txt or reward.json", () => {
    const d = (n: string) => join(tmp, "reward", n);
    write(join(d("txt"), "reward.txt"), "0.75\n");
    write(join(d("json"), "reward.json"), '{"reward": 1}');
    write(join(d("single"), "reward.json"), '{"accuracy": 0.5}');
    write(join(d("bad"), "reward.txt"), "n/a");
    mkdirSync(d("none"), { recursive: true });
    expect(harborReward(d("txt"))).toMatchObject({ score: 0.75, maxScore: 1, invalid: false });
    expect(harborReward(d("json")).score).toBe(1);
    expect(harborReward(d("single")).score).toBe(0.5);
    expect(harborReward(d("bad")).invalid).toBe(true);
    expect(harborReward(d("none"))).toMatchObject({ score: null, invalid: true });
  });
});

describe("ASI adapter", () => {
  it("reads the task_meta fields it needs", () => {
    const m = parseTaskMeta(`id: math.sigma
name: "Sigma" # comment
status: final
domain: math
difficulty:
  level: 3
  requires_gpu: true
output:
  files:
    - name: analysis.py
      description: x
    - name: 'results/solutions.csv'
  notes: y
`);
    expect(m).toEqual({
      id: "math.sigma",
      name: "Sigma",
      status: "final",
      domain: "math",
      requiresGpu: true,
      outputs: ["analysis.py", "results/solutions.csv"],
    });
  });

  it("builds an oracle command that copies reference outputs", () => {
    const t = oracleTemplate("/i n", ["a.py", "r/s.csv"]);
    expect(t).toContain("'/i n'/{instance_id}/reference {workspace} 'a.py' 'r/s.csv'");
  });

  it("recognizes model errors from the Agent CLI event stream", () => {
    const ev = (e: unknown) => `noise\n${JSON.stringify(e)}\n`;
    expect(modelError(ev({ type: "error", message: "401 invalid_api_key" }))).toBe(
      "model_authentication_failed",
    );
    expect(
      modelError(ev({ type: "turn.failed", error: { message: "The model x does not exist" } })),
    ).toBe("model_unavailable");
    expect(modelError(ev({ type: "error", message: "rate limited" }))).toBeNull();
    expect(modelError(null)).toBeNull();
  });

  it("scores the latest attempt and marks scorer or model failures invalid", () => {
    const ctx = {
      benchmark: {} as Benchmark,
      task: "math.sigma",
      method: { name: "c", agent: "codex" as const, auth: "p" },
      seed: 1,
      options: {},
      staging: tmp,
    };
    const solve = join(tmp, "asi-solve");
    const verify = join(tmp, "asi-verify");
    const inst = "math.sigma__seed31415";
    const native = (status: string, error = "") =>
      write(
        join(solve, "native", "math.sigma", `${inst}__b1.json`),
        JSON.stringify({
          instance_id: inst,
          prompt_level: "b1",
          status,
          agent_output: { error_message: error },
        }),
      );
    const report = (items: object[]) =>
      write(join(verify, "score.json"), JSON.stringify({ results: items }));
    const item = { instance_id: inst, prompt_level: "b1", max_score: 50 };

    expect(asiScore(ctx, solve, verify).issues).toEqual([
      "runner wrote no result for the instance",
    ]);
    native("completed");
    expect(asiScore(ctx, solve, verify).issues).toEqual(["scorer wrote no report"]);
    report([{ ...item, attempt: 1, final_score: 0 }]);
    // Nothing produced: still a valid zero, with the reason recorded.
    expect(asiScore(ctx, solve, verify)).toEqual({
      score: 0,
      maxScore: 50,
      issues: ["no declared output files produced"],
      invalid: false,
    });
    mkdirSync(join(solve, "native", "math.sigma", `${inst}__b1.outputs`), { recursive: true });
    report([
      { ...item, attempt: 1, final_score: 10 },
      { ...item, attempt: 2, final_score: 30 },
    ]);
    expect(asiScore(ctx, solve, verify)).toEqual({
      score: 30,
      maxScore: 50,
      issues: [],
      invalid: false,
    });
    report([{ ...item, final_score: 0, scorer_internal_error: true }]);
    expect(asiScore(ctx, solve, verify)).toMatchObject({
      invalid: true,
      issues: ["scorer_internal_error"],
    });
    native("failed", JSON.stringify({ type: "error", message: "authentication_error" }));
    report([{ ...item, final_score: 0 }]);
    expect(asiScore(ctx, solve, verify)).toMatchObject({
      invalid: true,
      issues: ["model_authentication_failed", "runner status failed"],
    });
  });
});

const run = (p: Partial<Run>): Run =>
  ({ state: "succeeded", startedAt: "t", reason: null, cleanup: "done", ...p }) as Run;

describe("outcome classification", () => {
  const score = { score: 1, maxScore: 1, issues: [], invalid: false };

  it("verifies failed and timed-out solves but not cancelled, lost or unstarted ones", () => {
    expect(solveVerdict(run({ state: "failed", reason: "timeout after 5 min" })).verify).toBe(true);
    expect(solveVerdict(run({ state: "cancelled" }))).toMatchObject({
      verify: false,
      evaluation: "unknown",
    });
    expect(solveVerdict(run({ state: "lost" }))).toMatchObject({
      verify: false,
      evaluation: "unknown",
    });
    expect(
      solveVerdict(run({ state: "failed", startedAt: null, reason: "build failed" })),
    ).toMatchObject({
      verify: false,
      evaluation: "invalid",
      issue: "environment failed: build failed",
    });
  });

  it("keeps execution, evaluation and cleanup apart", () => {
    const timedOut = classify(run({ state: "failed", reason: "timeout after 5 min" }), run({}), {
      ...score,
      score: 0,
    });
    expect(timedOut).toMatchObject({
      execution: "failed",
      evaluation: "valid",
      score: 0,
      issues: ["solve timed out"],
    });
    expect(classify(run({}), run({ state: "cancelled" }), null).evaluation).toBe("unknown");
    expect(classify(run({}), run({ startedAt: null }), null).evaluation).toBe("invalid");
    expect(
      classify(run({}), run({ state: "failed", reason: "timeout after 10 min" }), score).evaluation,
    ).toBe("invalid");
    expect(classify(run({}), run({}), { ...score, invalid: true }).evaluation).toBe("invalid");
    expect(classify(run({}), run({ cleanup: "failed" }), score)).toMatchObject({
      evaluation: "valid",
      cleanup: "failed",
    });
    expect(classify(run({}), null, null).evaluation).toBe("unknown");
  });
});

describe("aggregation", () => {
  const trial = (task: string, method: string, ev: "valid" | "invalid" | null, s = 0): Trial => ({
    id: `${task}.${method}`,
    jobId: "j",
    task,
    method,
    seed: 1,
    state: ev ? "done" : "solving",
    solveRunId: null,
    verifyRunId: null,
    issues: [],
    outcome: ev
      ? {
          execution: "succeeded",
          evaluation: ev,
          score: s,
          maxScore: 2,
          issues: [],
          cleanup: "done",
        }
      : null,
    createdAt: "t",
    endedAt: null,
  });
  const trials = [
    trial("a", "x", "valid", 2),
    trial("b", "x", "valid", 1),
    trial("a", "y", "valid", 0),
    trial("b", "y", "invalid", 2),
    trial("c", "y", null),
  ];

  it("averages only valid trials", () => {
    const [x, y] = summarize(["x", "y"], trials);
    expect(x).toMatchObject({ trials: 2, valid: 2, meanPct: 75 });
    expect(y).toMatchObject({ trials: 3, valid: 1, invalid: 1, pending: 1, meanPct: 0 });
  });

  it("compares methods on all valid tasks and on paired tasks", () => {
    const job = { id: "j", spec: { methods: [{ name: "x" }, { name: "y" }] } } as BenchJob;
    const c = compareJobs([{ job, trials }]);
    expect(c.columns.map((x) => x.key)).toEqual(["x", "y"]);
    expect(c.rows.find((r) => r.task === "b")?.counts).toEqual({ x: "1/1", y: "0/1" });
    expect(c.pairedTasks).toBe(1);
    expect(c.means.x).toEqual({ all: 75, paired: 100 });
    expect(c.means.y).toEqual({ all: 0, paired: 0 });
    const two = compareJobs([
      { job, trials },
      { job: { ...job, id: "k", spec: { ...job.spec, name: "rerun" } } as BenchJob, trials },
    ]);
    expect(two.columns.map((x) => x.key)).toEqual(["j/x", "j/y", "rerun/x", "rerun/y"]);
  });
});

describe("methods", () => {
  it("parses --method and builds Agent CLI commands", () => {
    expect(parseMethod("oracle")).toEqual({ name: "oracle", agent: "oracle" });
    expect(parseMethod("gpt=codex,auth=p,model=m,effort=high")).toEqual({
      name: "gpt",
      agent: "codex",
      auth: "p",
      model: "m",
      effort: "high",
    });
    expect(() => parseMethod("codex")).toThrow();
    expect(() => parseMethod("a=codex,foo=1")).toThrow(/unknown --method key/);
    expect(
      agentCommand({ name: "c", agent: "claude-code", auth: "p", model: "opus" }, "do"),
    ).toEqual(["claude", "-p", "--dangerously-skip-permissions", "--model", "opus", "do"]);
  });
});
