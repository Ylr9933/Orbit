// Trial outcome: execution (how the solve run ended), evaluation (whether the score can be trusted)
// and cleanup are kept apart. Only `valid` outcomes enter means; `unknown` means Orbit cannot tell
// (cancelled or lost), `invalid` means the environment or verifier failed to produce a real score.
import type { Outcome, Run } from "../contracts/index.ts";
import type { ScoreResult } from "./adapter.ts";

const cleanupOf = (...runs: (Run | null)[]): Outcome["cleanup"] => {
  const rs = runs.filter((r): r is Run => r !== null);
  if (rs.some((r) => r.cleanup === "failed")) return "failed";
  if (rs.some((r) => r.cleanup === "pending")) return "pending";
  return "done";
};

const timedOut = (r: Run) => r.state === "failed" && (r.reason ?? "").includes("timeout");

/** Whether the solve run got far enough that its result should be verified. */
export function solveVerdict(solve: Run): {
  verify: boolean;
  evaluation?: Outcome["evaluation"];
  issue?: string;
} {
  if (solve.state === "cancelled")
    return { verify: false, evaluation: "unknown", issue: "solve cancelled" };
  if (solve.state === "lost") return { verify: false, evaluation: "unknown", issue: "solve lost" };
  // Never started: the environment (image build, auth, lease) failed, not the method.
  if (solve.startedAt === null)
    return {
      verify: false,
      evaluation: "invalid",
      issue: `environment failed: ${solve.reason ?? "not started"}`,
    };
  // Timeouts and failures are the method's result; whatever it left behind is verified.
  return { verify: true };
}

export function classify(
  solve: Run,
  verify: Run | null,
  score: ScoreResult | null,
  issues: string[] = [],
): Outcome {
  const base = { execution: solve.state as string, maxScore: score?.maxScore ?? 1 };
  const all = [...issues];
  if (solve.state === "failed" && timedOut(solve)) all.push("solve timed out");
  const out = (
    evaluation: Outcome["evaluation"],
    s: number | null,
    extra: string[] = [],
  ): Outcome => ({
    ...base,
    evaluation,
    score: s,
    issues: [...all, ...extra],
    cleanup: cleanupOf(solve, verify),
  });
  const sv = solveVerdict(solve);
  if (!sv.verify) return out(sv.evaluation ?? "unknown", null, sv.issue ? [sv.issue] : []);
  if (!verify) return out("unknown", null, ["verify not run"]);
  if (verify.state === "cancelled" || verify.state === "lost")
    return out("unknown", null, [`verify ${verify.state}`]);
  if (verify.startedAt === null)
    return out("invalid", null, [`verifier environment failed: ${verify.reason ?? "not started"}`]);
  if (timedOut(verify)) return out("invalid", null, ["verify timed out"]);
  if (!score) return out("invalid", null, ["no score"]);
  if (score.invalid || score.score === null) return out("invalid", score.score, score.issues);
  return out("valid", score.score, score.issues);
}
