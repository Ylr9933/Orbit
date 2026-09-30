// What a benchmark adapter provides to BenchService: its task list, the solve and verify runs of a
// trial, and the score read from the verify run's output. Adapters stay pure file/spec builders;
// submitting, watching and classifying runs is BenchService's job.
import type { Benchmark, BenchTask, Method, Run, RunSpecInput } from "../contracts/index.ts";

export interface ScoreResult {
  score: number | null;
  maxScore: number;
  issues: string[];
  /** The verifier could not produce a trustworthy score (missing reward, scorer error...). */
  invalid: boolean;
}

export interface TrialContext {
  benchmark: Benchmark;
  task: string;
  method: Method;
  seed: number;
  options: Record<string, string>;
  timeoutMin?: number;
  /** Private per-trial directory for copies mounted into runs (`~/.orbit/bench/<job>/<trial>`). */
  staging: string;
}

export interface VerifyPlan {
  spec: RunSpecInput;
  /** Recorded on the trial (e.g. artifacts the solve run did not produce). */
  issues: string[];
}

export interface Adapter {
  tasks(b: Benchmark): BenchTask[];
  solveSpec(ctx: TrialContext): RunSpecInput;
  verifySpec(ctx: TrialContext, solve: Run, solveOutput: string): VerifyPlan;
  score(ctx: TrialContext, solve: Run, solveOutput: string, verifyOutput: string): ScoreResult;
}

/** Headless Agent CLI invocation with full permissions (the container is the sandbox). */
export function agentCommand(method: Method, instruction: string): string[] {
  if (method.agent === "codex") {
    const cmd = [
      "codex",
      "exec",
      "--skip-git-repo-check",
      "--dangerously-bypass-approvals-and-sandbox",
    ];
    if (method.model) cmd.push("--model", method.model);
    if (method.effort) cmd.push("-c", `model_reasoning_effort="${method.effort}"`);
    return [...cmd, instruction];
  }
  if (method.agent === "claude-code") {
    const cmd = ["claude", "-p", "--dangerously-skip-permissions"];
    if (method.model) cmd.push("--model", method.model);
    return [...cmd, instruction];
  }
  throw new Error(`${method.agent} is not an Agent CLI`);
}
