import assert from "node:assert/strict";
import test from "node:test";
import {
  csv,
  groupSteps,
  configDiff,
  outcome,
} from "../../src/web/src/features/benchmark/utils.ts";

test("CSV preserves zero/missing and neutralizes spreadsheet formulas", () => {
  const value = csv([
    ["task", "score"],
    ["=SUM(A1)", 0],
    ["missing", null],
    ['a,b"c', -2],
  ]);
  assert(value.includes('"\'=SUM(A1)","0"'));
  assert(value.includes('"missing",""'));
  assert(value.includes('"a,b""c","-2"'));
});
test("trajectory pairing uses explicit call identity and keeps unpaired steps", () => {
  const step = (i, type, id) => ({
    step_index: i,
    step_type: type,
    content: "",
    metadata: id ? { tool_call_id: id } : {},
  });
  const values = groupSteps([
    step(0, "tool_call", "a"),
    step(1, "tool_result", "b"),
    step(2, "tool_result", "a"),
    step(3, "tool_call"),
  ]);
  assert.equal(values.length, 3);
  assert.equal(values[0].response.step_index, 2);
  assert.equal(values[1].response, undefined);
});
test("configuration diff and zero score do not disguise runtime failures", () => {
  assert.deepEqual(
    configDiff({ a: { model: "old" } }, { a: { model: "new" } }),
    [{ field: "a.model", left: '"old"', right: '"new"' }],
  );
  assert.equal(
    outcome({ state: "finished", score_valid: true, metrics: { score: 0 } }),
    "已评分",
  );
  assert.equal(
    outcome({ state: "finished", execution: "failed", score_valid: false }),
    "执行失败",
  );
});

test("workbench score semantics, filters and pagination preserve all valid results", async () => {
  const { resultStats, resultRows, pageNumber } = await import(
    "../../src/web/src/features/benchmark/presentation.ts"
  );
  const make = (id, value, extra = {}) => ({
    unit_id: id,
    model: "model",
    state: "finished",
    score_valid: true,
    metrics: { score: value },
    annotation: {},
    elapsed_seconds: 59.6,
    ...extra,
  });
  const rows = [
    make("math.a__seed1", 0),
    make("math.b__seed1", 10),
    make("physics.c__seed1", 100),
    make("physics.failed", 500, { score_valid: false, execution: "failed" }),
    make("missing", undefined),
  ];
  assert.deepEqual(resultStats(rows, "score"), {
    count: 3,
    mean: 110 / 3,
    median: 10,
    zero: 1,
    duration: 59.6,
  });
  assert.equal(resultRows(rows, "score", { filter: "zero" }).length, 1);
  assert.equal(resultRows(rows, "score", { filter: "failed" }).length, 1);
  assert.equal(resultRows(rows, "score", { filter: "unscored" }).length, 2);
  assert.equal(
    resultRows(rows, "score", { domain: "数学", search: "seed1" }).length,
    2,
  );
  assert.deepEqual(
    resultRows(rows, "score", { sort: "high" })
      .slice(0, 3)
      .map((r) => r.metrics.score),
    [100, 10, 0],
  );
  assert.equal(pageNumber("NaN", 60, 20), 0);
  assert.equal(pageNumber("-1", 60, 20), 0);
  assert.equal(pageNumber("999", 60, 20), 2);
  assert.equal(pageNumber("0", 0, 20), 0);
});
test("human readable time and configuration do not confuse outer budget with solver timeout", async () => {
  const { duration, number } = await import(
    "../../src/web/src/features/benchmark/utils.ts"
  );
  const { taskTimeout, configFields, taskLabel, batchConditions } =
    await import("../../src/web/src/features/benchmark/presentation.ts");
  assert.equal(number(0.00001), "1.00e-5");
  assert.equal(duration(59.6), "1 分 0 秒");
  assert.equal(duration(119.9), "2 分 0 秒");
  assert.equal(duration(null), "—");
  assert.equal(
    taskTimeout({
      config: { parameters: { timeout_seconds: "10800" } },
      budget_seconds: 10920,
    }),
    10800,
  );
  assert.equal(taskTimeout({ config: {}, budget_seconds: 10920 }), null);
  assert.equal(taskLabel("math.linear_program__seed31415"), "linear program");
  assert.equal(taskLabel("other.task_id"), "other.task_id");
  assert.equal(
    configFields({
      config: { resources: { gpu_count: 0 } },
      model: "m",
      agent: "a",
      benchmark: "b",
    }).find(([k]) => k === "GPU")[1],
    "0",
  );
  assert.equal(
    batchConditions([
      { config: { parameters: { effort: "medium" } } },
      { config: {} },
    ]),
    "思考强度 medium（部分任务未记录）",
  );
});
