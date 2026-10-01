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
 * `ORBIT_AGENT=<harness>[:<sessionId>]` overrides detection. When agents are nested (Claude Code
 * starting Codex or vice versa) the child inherits the parent's variables, so the nearest agent
 * process among the ancestors decides; environment variables are the fallback.
 */
export function detectAgent(
  env: NodeJS.ProcessEnv = process.env,
  cwd = process.cwd(),
  parents: string[] = ancestors(),
): AgentRef | undefined {
  if (env.ORBIT_AGENT) {
    const i = env.ORBIT_AGENT.indexOf(":");
    const h = i < 0 ? env.ORBIT_AGENT : env.ORBIT_AGENT.slice(0, i);
    const sessionId = i < 0 ? "" : env.ORBIT_AGENT.slice(i + 1);
    const harness = h === "claude-code" || h === "codex" ? h : "other";
    return { harness, sessionId: sessionId || undefined, cwd };
  }
  const claude = env.CLAUDECODE === "1" || !!env.CLAUDE_CODE_SESSION_ID;
  const codexId = env.CODEX_THREAD_ID || env.CODEX_SESSION_ID;
  const nearest = parents.find((n) => n === "claude" || n.startsWith("codex"));
  const harness = nearest
    ? nearest === "claude"
      ? "claude-code"
      : "codex"
    : claude
      ? "claude-code"
      : codexId
        ? "codex"
        : undefined;
  if (harness === "claude-code") {
    return { harness, sessionId: env.CLAUDE_CODE_SESSION_ID || undefined, cwd };
  }
  if (harness === "codex") return { harness, sessionId: codexId || undefined, cwd };
  return undefined;
}
