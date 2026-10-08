import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { handle } from "../src/bench/adapter.ts";
import {
  asiScore,
  modelError,
  oracleTemplate,
  parseTaskMeta,
  scorerIssues,
} from "../src/bench/asi.ts";
import { classify, solveVerdict } from "../src/bench/classify.ts";
import {
  findHarborTasks,
  harborAdapter,
  harborReward,
  harborSolveSpec,
  harborVerifySpec,
  parseArtifacts,
} from "../src/bench/harbor.ts";
import { AdapterClient, callAdapter, toRunSpec } from "../src/bench/protocol.ts";
import {
  applyOverride,
  loadResources,
  resolveResources,
  taskOverride,
  usageRow,
} from "../src/bench/resources.ts";
import { compareJobs, summarize } from "../src/bench/service.ts";
import { parseMethod } from "../src/cli/bench.ts";
import {
  AdapterRunSpec,
  type BenchJob,
  type Benchmark,
  type Run,
  type Trial,
} from "../src/contracts/index.ts";
import { agentCommand, agentErrorKind } from "../src/harness/index.ts";
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
    const req = { protocol: 1 as const, op: "tasks" as const };
    const reply = handle(harborAdapter, {
      ...req,
      benchmark: { name: "t", path: root, config: {} },
    });
    expect((reply as { tasks: { id: string }[] }).tasks.map((t) => t.id)).toContain("sr");
    expect(() =>
      handle(harborAdapter, {
        ...req,
        op: "solve",
        benchmark: { name: "t", path: root, config: {} },
      }),
    ).toThrow(/solve request without trial/);
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
    // The adapter only gives the instruction; Orbit turns it into the Agent CLI command.
    expect(agent.command).toBeUndefined();
    expect(agent.agentTask).toEqual({ instruction: "x\n" });
    expect(agent.timeoutMin).toBe(5);

    const solveOut = join(tmp, "solve-out");
    const plan0 = harborVerifySpec(t, solveOut, staging);
    expect(plan0.missing).toEqual(["/app/out"]);
    write(join(solveOut, "collected", "app", "out", "result.txt"), "42\n");
    const plan = harborVerifySpec(t, solveOut, staging);
    expect(plan.missing).toEqual([]);
    expect(plan.spec.timeoutMin).toBe(2);
    expect(plan.spec.collect).toEqual(["/logs/verifier"]);
    expect(JSON.stringify(plan.spec.mounts)).toContain("/app/out");
  });

  it("lets Orbit add the Agent command, auth, env and grader secrets", () => {
    const t = findHarborTasks(root).find((x) => x.id === "sr");
    if (!t) throw new Error("task missing");
    const b = {
      name: "tbs",
      adapter: "harbor",
      path: root,
      config: {},
      env: { B: "1" },
      passEnv: ["GRADER_KEY"],
    } as unknown as Benchmark;
    const staging = join(tmp, "staging-pe");
    const codex = { name: "c", agent: "codex" as const, auth: "p", bundle: "/m", model: "m" };
    const oracle = { name: "oracle", agent: "oracle" as const };

    const agent = toRunSpec(harborSolveSpec(t, codex, staging), codex, b, "solve");
    expect(agent.command?.slice(0, 2)).toEqual(["codex", "exec"]);
    expect(agent.command?.at(-1)).toBe("x\n");
    expect(agent).toMatchObject({ auth: "p", agentBundle: "/m", network: true, snapshot: false });
    expect(agent.env).toEqual({ B: "1" });
    expect(agent.passEnv ?? []).toEqual([]);

    const solve = toRunSpec(harborSolveSpec(t, oracle, staging), oracle, b, "solve");
    expect(solve.auth).toBeUndefined();
    expect(solve.env).toEqual({ B: "1", SEED: "1" });
    const verify = toRunSpec(
      harborVerifySpec(t, join(tmp, "solve-out"), staging).spec,
      oracle,
      b,
      "verify",
    );
    expect(verify).toMatchObject({ passEnv: ["GRADER_KEY"], priority: 1 });

    const task = { agentTask: { instruction: "go" }, image: "x" };
    expect(() => toRunSpec(task, oracle, b, "solve")).toThrow(/asked for an Agent/);
    expect(() => toRunSpec(task, codex, b, "verify")).toThrow(/cannot ask for an Agent/);
    expect(() => toRunSpec({ command: ["true"] }, oracle, b, "solve")).toThrow(/image/);
    expect(AdapterRunSpec.safeParse({ command: ["true"], auth: "p" }).success).toBe(false);
    expect(AdapterRunSpec.safeParse({ image: "x" }).success).toBe(false);
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

describe("adapter protocol", () => {
  // An external adapter: answers each op from the request, or misbehaves on demand via config.
  const script = join(tmp, "adapter.mjs");
  write(
    script,
    `#!${process.execPath}
let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  const req = JSON.parse(input);
  const mode = req.benchmark.config.mode;
  if (mode === "fail") { console.error("no tasks here"); process.exit(3); }
  if (mode === "garbage") return console.log("not json");
  if (mode === "sleep") return setTimeout(() => {}, 10000);
  if (mode === "secret") return console.log(JSON.stringify({ tasks: [{ id: String(process.env.SECRET_KEY), title: null, supported: true, reason: null }] }));
  if (process.argv[2] !== req.op) process.exit(9);
  if (req.op === "tasks")
    return console.log(JSON.stringify({ tasks: [{ id: "a", title: req.benchmark.path, supported: true, reason: null }] }));
  if (req.op === "solve") return console.log(JSON.stringify({ spec: { image: "x", agentTask: { instruction: req.trial.task } } }));
  if (req.op === "verify") return console.log(JSON.stringify({ spec: { image: "x", command: ["true"] }, issues: ["w"] }));
  console.log(JSON.stringify({ score: req.verify.run.exitCode === 0 ? 1 : 0 }));
});
`,
  );
  chmodSync(script, 0o755);
  const bench = (config: Record<string, string> = {}) =>
    ({
      name: "x",
      adapter: script,
      path: tmp,
      config,
      env: {},
      passEnv: [],
    }) as unknown as Benchmark;
  const trial = {
    id: "j.1",
    task: "a",
    method: { name: "c", agent: "codex" as const, auth: "p" },
    seed: 1,
    options: {},
    staging: tmp,
    hostNetwork: false,
  };

  it("runs each op with the request on stdin and validates the reply", async () => {
    const c = new AdapterClient(bench(), undefined);
    expect(await c.tasks()).toEqual({
      tasks: [{ id: "a", title: tmp, supported: true, reason: null, tags: {} }],
      metrics: [],
    });
    expect((await c.solve(trial)).spec).toMatchObject({ agentTask: { instruction: "a" } });
    const ref = { run: run({ exitCode: 0 }), output: tmp };
    expect((await c.verify(trial, ref)).issues).toEqual(["w"]);
    expect(await c.score(trial, ref, ref)).toEqual({
      score: 1,
      maxScore: 1,
      invalid: false,
      issues: [],
    });
  });

  it("reports failures, bad replies and timeouts, and keeps daemon secrets away", async () => {
    await expect(new AdapterClient(bench({ mode: "fail" }), undefined).tasks()).rejects.toThrow(
      /adapter tasks: exit 3: no tasks here/,
    );
    await expect(new AdapterClient(bench({ mode: "garbage" }), undefined).tasks()).rejects.toThrow(
      /not one JSON value/,
    );
    const req = { protocol: 1 as const, op: "tasks" as const, benchmark: bench({ mode: "sleep" }) };
    await expect(callAdapter([script], tmp, req, 300)).rejects.toThrow(/timed out/);
    process.env.SECRET_KEY = "s3cret";
    try {
      const ts = await new AdapterClient(bench({ mode: "secret" }), undefined).tasks();
      expect(ts.tasks[0]?.id).toBe("undefined");
    } finally {
      delete process.env.SECRET_KEY;
    }
    expect(() => new AdapterClient({ ...bench(), adapter: "harbor" }, undefined)).toThrow(
      /built-in adapters are not available/,
    );
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
    // Quota; reconnect notices are not the outcome, the final turn.failed is.
    const quota = "You've hit your usage limit. Try again later.";
    expect(modelError(ev({ type: "turn.failed", error: { message: quota } }))).toBe(
      "model_quota_exhausted",
    );
    const retried = [
      { type: "error", message: "Reconnecting... 1/5 (401 Unauthorized: invalid_api_key)" },
      { type: "turn.failed", error: { message: "unexpected status 401 Unauthorized" } },
    ];
    expect(modelError(retried.map((e) => JSON.stringify(e)).join("\n"))).toBe(
      "model_authentication_failed",
    );
    expect(
      modelError(JSON.stringify({ type: "error", message: "Reconnecting... 2/5 (usage limit)" })),
    ).toBeNull();
  });

  it("names why an Agent CLI could not work, and nothing else", () => {
    expect(agentErrorKind("unexpected status 401 Unauthorized: Incorrect API key")).toBe(
      "model_authentication_failed",
    );
    expect(agentErrorKind("insufficient_quota")).toBe("model_quota_exhausted");
    expect(agentErrorKind("Credit balance is too low")).toBe("model_quota_exhausted");
    expect(agentErrorKind("The 'x' model is not supported when using Codex")).toBe(
      "model_unavailable",
    );
    expect(agentErrorKind("stream disconnected before completion: Connection reset")).toBe(
      "model_unreachable",
    );
    expect(agentErrorKind("python: No module named numpy")).toBeNull();
    expect(agentErrorKind("Model metadata for x not found")).toBeNull();
  });

  it("finds judge and file problems inside an ASI score item", () => {
    expect(
      scorerIssues({
        gate_results: [{ scorer_name: "g", details: { error: "FileNotFoundError: pred/a.npy" } }],
        score_results: [
          { scorer_name: "judge", details: { evaluator_unavailable: true, error: "400" } },
          { scorer_name: "ok", details: { error: null } },
          { scorer_name: "m", message: "open: No such file or directory", details: null },
        ],
      }),
    ).toEqual({ judgeUnavailable: ["judge"], missingFile: ["g", "m"] });
    expect(scorerIssues({})).toEqual({ judgeUnavailable: [], missingFile: [] });
  });

  it("scores the latest attempt and marks scorer or model failures invalid", () => {
    const ctx = {
      id: "j.00001",
      task: "math.sigma",
      method: { name: "c", agent: "codex" as const, auth: "p" },
      seed: 1,
      options: {},
      staging: tmp,
      hostNetwork: false,
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
      metrics: { fullMarks: 0 },
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
      metrics: { fullMarks: 0 },
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
    native("completed");
    report([
      {
        ...item,
        final_score: 20,
        score_results: [{ scorer_name: "llm", details: { evaluator_unavailable: true } }],
        gate_results: [{ scorer_name: "files", details: { error: "No such file or directory" } }],
      },
    ]);
    // A judge that could not run makes the score untrustworthy; a missing file alone is a note.
    expect(asiScore(ctx, solve, verify)).toMatchObject({
      invalid: true,
      score: 20,
      issues: ["judge unavailable: llm", "scorer could not find a file: files"],
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
    // The Agent could not work (credentials, quota, ...): the score is kept but not trusted.
    const agent = { kind: "model_quota_exhausted", message: "usage limit" };
    expect(classify(run({}), run({}), { ...score, score: 0 }, [], agent)).toMatchObject({
      evaluation: "invalid",
      score: 0,
      issues: ["Agent stopped: model_quota_exhausted (usage limit)"],
    });
    expect(classify(run({}), run({}), score, [], null).evaluation).toBe("valid");
  });

  it("makes an out-of-memory solve invalid and notes memory kills of a surviving run", () => {
    const usage = {
      samples: 3,
      peakMemGB: 15.9,
      peakCpus: 2,
      meanCpus: 1,
      peakGpuMemGB: null,
      oomKills: 1,
      oomKilled: true,
    };
    const spec = { resources: { memGB: 16 } } as Run["spec"];
    const oom = classify(run({ state: "failed", spec, usage }), run({}), { ...score, score: 0 });
    expect(oom).toMatchObject({ evaluation: "invalid", score: 0 });
    expect(oom.issues).toEqual(["ran out of memory (limit 16 GB, peak 15.9 GB)"]);
    const survived = classify(run({ spec, usage: { ...usage, oomKilled: false } }), run({}), score);
    expect(survived).toMatchObject({ evaluation: "valid" });
    expect(survived.issues).toEqual(["1 process(es) in the solve run killed for memory"]);
  });
});

describe("resources file", () => {
  const file = join(tmp, "resources.json");
  const doc = {
    version: 1,
    default: { cpus: 4, memGB: 16, gpus: 0, timeoutMin: 240 },
    tasks: {
      big: { gpus: 1, gpuMemGB: 12, memGB: 32, evidence: "trains a GNN", confidence: "high" },
    },
  };

  it("validates, merges task over default and drops the human-only fields", () => {
    write(file, JSON.stringify(doc));
    const r = loadResources(file);
    expect(taskOverride(r, "big")).toEqual({
      cpus: 4,
      memGB: 32,
      gpus: 1,
      gpuMemGB: 12,
      timeoutMin: 240,
    });
    expect(taskOverride(r, "small")).toEqual({ cpus: 4, memGB: 16, gpus: 0, timeoutMin: 240 });
    expect(() => resolveResources(r, ["small"], ["small"])).toThrow(/unknown tasks: big/);
    write(file, JSON.stringify({ ...doc, tasks: { big: { memGb: 32 } } }));
    expect(() => loadResources(file)).toThrow(/tasks\.big: .*memGb/);
    write(file, "{");
    expect(() => loadResources(file)).toThrow(/resources file/);
  });

  it("overrides the adapter's solve resources; --timeout keeps the timeout", () => {
    const spec = {
      image: "x",
      command: ["true"],
      resources: { cpus: 8, memGB: 32 },
      timeoutMin: 60,
    };
    const o = { cpus: 4, memGB: 16, gpus: 1, timeoutMin: 240 };
    expect(applyOverride(spec, o, false)).toMatchObject({
      resources: { cpus: 4, memGB: 16, gpus: 1 },
      timeoutMin: 240,
    });
    expect(applyOverride(spec, o, true).timeoutMin).toBe(60);
    expect(applyOverride(spec, undefined, false)).toBe(spec);
  });

  it("suggests from measured peaks with headroom, after OOMs and timeouts, never GPUs", () => {
    const req = { cpus: 4, memGB: 16, gpus: 1, gpuMemGB: 8, timeoutMin: 60 };
    const measured = (u: Partial<NonNullable<Run["usage"]>>, p: Partial<Run> = {}) =>
      run({
        startedAt: "2026-01-01T00:00:00Z",
        endedAt: "2026-01-01T01:00:00Z",
        usage: {
          samples: 5,
          peakMemGB: 14,
          peakCpus: 6.5,
          meanCpus: 1,
          peakGpuMemGB: 9,
          oomKills: 0,
          oomKilled: false,
          ...u,
        },
        ...p,
      });
    const row = usageRow("t", req, [measured({}), measured({ peakMemGB: 10 })]);
    expect(row).toMatchObject({ runs: 2, peakMemGB: 14, maxMinutes: 60 });
    expect(row.suggest).toEqual({ memGB: 24, gpuMemGB: 12, cpus: 8, timeoutMin: 120 });
    const oom = usageRow("t", { ...req, memGB: 48 }, [measured({ peakMemGB: 2, oomKilled: true })]);
    expect(oom.suggest.memGB).toBe(64);
    expect(oom.notes[0]).toMatch(/killed for memory/);
    const quiet = measured({ peakMemGB: 3, peakGpuMemGB: 0.1 });
    expect(usageRow("t", { ...req, memGB: 64 }, [quiet]).suggest.memGB).toBeUndefined();
    const small = usageRow("t", { ...req, memGB: 64 }, [quiet, quiet]);
    expect(small.suggest.memGB).toBe(4);
    expect(small.notes.join()).toMatch(/hardly used/);
    expect(small.suggest).not.toHaveProperty("gpus");
    const timeout = usageRow("t", req, [
      measured({}, { state: "failed", reason: "timeout after 60 min" }),
    ]);
    expect(timeout.suggest.timeoutMin).toBe(120);
    expect(usageRow("t", req, [run({})]).notes).toEqual(["no measured runs"]);
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
          review: null,
        }
      : null,
    history: [],
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
    expect(x).toMatchObject({ trials: 2, valid: 2 });
    expect(x?.metrics.score).toMatchObject({ mean: 75, tasks: 2, trials: 2 });
    expect(y).toMatchObject({ trials: 3, valid: 1, invalid: 1, pending: 1 });
    expect(y?.metrics.score).toMatchObject({ mean: 0, tasks: 1, se: null, ci: null });
  });

  it("compares methods on all valid tasks and on paired tasks", () => {
    const job = {
      id: "j",
      spec: { methods: [{ name: "x" }, { name: "y" }] },
      metrics: [],
    } as unknown as BenchJob;
    const c = compareJobs([{ job, trials }]);
    expect(c.columns.map((x) => x.key)).toEqual(["x", "y"]);
    expect(c.rows.find((r) => r.task === "b")?.counts).toEqual({ x: "1/1", y: "0/1" });
    const st = c.stats.score;
    expect(st?.pairedTasks).toBe(1);
    expect([st?.columns.x?.all?.mean, st?.columns.x?.paired?.mean]).toEqual([75, 100]);
    expect([st?.columns.y?.all?.mean, st?.columns.y?.paired?.mean]).toEqual([0, 0]);
    expect(st?.columns.y?.diff).toMatchObject({ mean: -100, tasks: 1, se: null });
    const two = compareJobs([
      { job, trials },
      { job: { ...job, id: "k", spec: { ...job.spec, name: "rerun" } } as BenchJob, trials },
    ]);
    expect(two.columns.map((x) => x.key)).toEqual(["j/x", "j/y", "rerun/x", "rerun/y"]);
    const named = { ...job, spec: { ...job.spec, name: "same" } } as BenchJob;
    const dup = compareJobs([
      { job: named, trials },
      { job: { ...named, id: "k" }, trials },
    ]);
    expect(dup.columns.map((x) => x.key)).toEqual(["same/x", "same/y", "k/x", "k/y"]);
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

describe("review", () => {
  it("validates declared files and items, keeps unknown fields and clips long text", async () => {
    const { ScoreResult } = await import("../src/contracts/index.ts");
    const r = ScoreResult.parse({
      score: 1,
      review: {
        files: [
          {
            label: "Report",
            phase: "solve",
            path: "a/report.md",
            kind: "notebook",
            fallback: "markdown",
            extra: 1,
          },
        ],
        items: [{ criterion: "c", score: 5, reasoning: "x".repeat(30_000) }],
        details: { model: "m", attempts: 3 },
        futureField: [1, 2],
      },
    });
    expect(r.review?.files[0]).toMatchObject({ kind: "notebook", fallback: "markdown", extra: 1 });
    expect(r.review?.items[0]?.reasoning?.length).toBe(20_001);
    expect((r.review as Record<string, unknown>).futureField).toEqual([1, 2]);
    for (const path of ["/etc/passwd", "../x", "a/../../b"])
      expect(
        ScoreResult.safeParse({
          score: 1,
          review: { files: [{ label: "x", phase: "solve", path }] },
        }).success,
      ).toBe(false);
    expect(
      ScoreResult.safeParse({
        score: 1,
        review: { files: [{ label: "x", phase: "solve", path: "a", fallback: "html" }] },
      }).success,
    ).toBe(false);
    expect(ScoreResult.parse({ score: 1 }).review).toBeUndefined();
  });

  it("keeps the review on the outcome, also when the score is not trusted", () => {
    const review = { files: [], items: [{ criterion: "c" }], details: {} };
    expect(
      classify(run({}), run({}), { score: 1, maxScore: 1, issues: [], invalid: false, review })
        .review,
    ).toEqual(review);
    expect(
      classify(run({}), run({}), { score: 0, maxScore: 1, issues: [], invalid: true, review })
        .review,
    ).toEqual(review);
    expect(classify(run({}), null, null).review).toBeNull();
  });
});
