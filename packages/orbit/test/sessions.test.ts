import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  findCodexSession,
  loadTranscript,
  parseClaude,
  parseCodex,
} from "../src/sessions/index.ts";

const root = mkdtempSync(join(tmpdir(), "orbit-sessions-"));
const roots = { claude: join(root, "claude"), codex: join(root, "codex") };
const jl = (rows: unknown[]) => `${rows.map((r) => JSON.stringify(r)).join("\n")}\n`;

describe("claude code transcripts", () => {
  it("normalizes text, thinking, tool calls and results; skips sidechains", async () => {
    mkdirSync(join(roots.claude, "-p"), { recursive: true });
    const f = join(roots.claude, "-p", "s1.jsonl");
    writeFileSync(
      f,
      jl([
        { type: "mode" },
        { type: "user", timestamp: "t1", message: { content: "run a sweep" } },
        {
          type: "assistant",
          timestamp: "t2",
          message: {
            content: [
              { type: "thinking", thinking: "plan" },
              { type: "tool_use", id: "u1", name: "Bash", input: { command: "orbit run" } },
            ],
          },
        },
        {
          type: "user",
          message: { content: [{ type: "tool_result", tool_use_id: "u1", content: "ok" }] },
        },
        { type: "assistant", isSidechain: true, message: { content: "hidden" } },
      ]),
    );
    const m = await parseClaude(f);
    expect(m.map((x) => `${x.role}/${x.kind}/${x.name ?? ""}`)).toEqual([
      "user/text/",
      "assistant/thinking/",
      "assistant/tool_call/Bash",
      "tool/tool_result/Bash",
    ]);
    const t = await loadTranscript({ harness: "claude-code", sessionId: "s1" }, roots);
    expect(t?.messages).toHaveLength(4);
  });
});

describe("codex transcripts", () => {
  it("finds a session by cwd and parses response items", async () => {
    const d = join(roots.codex, "2026", "09", "30");
    mkdirSync(d, { recursive: true });
    const f = join(d, "rollout-2026-09-30T10-00-00-abc.jsonl");
    writeFileSync(
      f,
      jl([
        { type: "session_meta", payload: { id: "abc", cwd: "/proj" } },
        {
          type: "response_item",
          payload: { type: "message", role: "user", content: [{ type: "input_text", text: "hi" }] },
        },
        {
          type: "response_item",
          payload: { type: "function_call", name: "shell", call_id: "c1", arguments: "{}" },
        },
        {
          type: "response_item",
          payload: { type: "function_call_output", call_id: "c1", output: "done" },
        },
        { type: "event_msg", payload: { type: "token_count" } },
      ]),
    );
    expect(await findCodexSession(roots, { cwd: "/proj" })).toEqual({ file: f, sessionId: "abc" });
    expect(await findCodexSession(roots, { cwd: "/other" })).toBeNull();
    const m = await parseCodex(f);
    expect(m.map((x) => `${x.kind}/${x.name ?? ""}`)).toEqual([
      "text/",
      "tool_call/shell",
      "tool_result/shell",
    ]);
  });
});
