import assert from "node:assert/strict";
import test from "node:test";
import {
  filterTimeline,
  groupTimeline,
  timelineDuration,
  timelineStatus,
  timelineTone,
} from "../../src/web/src/features/execution-trace.ts";

const at = "2026-09-21T08:29:01.000Z";
const event = (id, type, payload = {}, producer = "environment", time = at) => ({
  id,
  type,
  payload,
  producer,
  at: time,
  capture_status: "complete",
  text: "",
});

test("research timeline highlights the experiment while retaining every public event", () => {
  const timeline = groupTimeline([
    event("lease", "lease.granted", { node_id: "prompt" }),
    event("start", "tool.requested", { tool_call_id: "1", tool_name: "start" }),
    event(
      "started",
      "tool.completed",
      { tool_call_id: "1", tool_name: "start" },
      "environment",
      "2026-09-21T08:29:02.250Z",
    ),
    event("logs", "tool.requested", { tool_call_id: "2", tool_name: "logs" }),
    event("logged", "tool.completed", { tool_call_id: "2", tool_name: "logs" }),
    event("exit", "process.exited", { job_id: "1234567890", status: "rejected" }),
    event("agent", "agent.message", { role: "assistant" }, "agent"),
  ]);

  assert.equal(timeline.length, 5);
  assert.deepEqual(
    filterTimeline(timeline, "highlights").map((item) => item.event.id),
    ["lease", "start", "exit", "agent"],
  );
  assert.equal(filterTimeline(timeline, "all").length, 5);
  assert.equal(filterTimeline(timeline, "tools").length, 2);
  assert.deepEqual(
    filterTimeline(timeline, "agent").map((item) => item.event.id),
    ["agent"],
  );
  assert.equal(timelineDuration(timeline[1]), "1.3 秒");
  assert.equal(timelineStatus(timeline[3]), "被拒绝");
  assert.equal(timelineTone(timeline[3]), "warning");
});

test("tool responses only pair with the same producer and call ID", () => {
  const timeline = groupTimeline([
    event("platform", "tool.requested", { tool_call_id: "same", tool_name: "start" }),
    event(
      "agent-result",
      "tool.completed",
      { tool_call_id: "same", tool_name: "shell" },
      "agent",
    ),
  ]);
  assert.equal(timeline.length, 2);
  assert.equal(timelineStatus(timeline[0]), "本页未见响应");
});

test("routine tool failures remain in highlights", () => {
  const timeline = groupTimeline([
    event("request", "tool.requested", { tool_call_id: "logs-1", tool_name: "logs" }),
    event("failure", "tool.completed", {
      tool_call_id: "logs-1",
      tool_name: "logs",
      is_error: true,
    }),
  ]);
  assert.equal(filterTimeline(timeline, "highlights").length, 1);
  assert.equal(timelineStatus(timeline[0]), "调用失败");
  assert.equal(timelineTone(timeline[0]), "warning");
});
