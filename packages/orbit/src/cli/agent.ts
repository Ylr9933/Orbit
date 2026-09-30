import { readFileSync } from "node:fs";
import type { AgentRef } from "../contracts/index.ts";

/** Parent process names, nearest first (Linux /proc). */
function ancestors(max = 12): string[] {
  const names: string[] = [];
  let pid = process.ppid;
  for (let i = 0; i < max && pid > 1; i++) {
    try {
      const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
      const open = stat.indexOf("(");
      const close = stat.lastIndexOf(")");
      names.push(stat.slice(open + 1, close));
      pid = Number(stat.slice(close + 2).split(" ")[1]);
    } catch {
      break;
    }
  }
  return names;
}

/**
 * Identify the coding agent that invoked the CLI, so runs link to its session transcript.
 * `ORBIT_AGENT=<harness>[:<sessionId>]` overrides detection.
 */
export function detectAgent(
  env: NodeJS.ProcessEnv = process.env,
  cwd = process.cwd(),
): AgentRef | undefined {
  if (env.ORBIT_AGENT) {
    const [h, sessionId] = env.ORBIT_AGENT.split(":", 2);
    const harness = h === "claude-code" || h === "codex" ? h : "other";
    return { harness, sessionId: sessionId || undefined, cwd };
  }
  if (env.CLAUDECODE === "1" || env.CLAUDE_CODE_SESSION_ID) {
    return { harness: "claude-code", sessionId: env.CLAUDE_CODE_SESSION_ID || undefined, cwd };
  }
  const codexId = env.CODEX_SESSION_ID || env.CODEX_THREAD_ID;
  if (codexId || ancestors().some((n) => n.startsWith("codex"))) {
    return { harness: "codex", sessionId: codexId || undefined, cwd };
  }
  return undefined;
}
