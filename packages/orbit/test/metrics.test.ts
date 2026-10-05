import { describe, expect, it } from "vitest";
import { AdapterTasksResponse, ScoreResult } from "../src/contracts/index.ts";
import {
  aggregate,
  fmtCi,
  fmtMetric,
  goodness,
  metricValue,
  pairedDiff,
  primaryMetric,
  resolveMetrics,
  SCORE_METRIC,
  taskMeans,
  verdict,
} from "../src/contracts/metrics.ts";

const o = (score: number | null, metrics?: Record<string, number>) => ({
  score,
  maxScore: 4,
  metrics,
});

describe("bench metrics", () => {
  it("resolves declarations: score first, exactly one primary, score keeps its value range", () => {
    expect(resolveMetrics([])).toEqual([SCORE_METRIC]);
    const ms = resolveMetrics([
      { name: "cost", label: "Cost", unit: "$", higherIsBetter: false, primary: false },
      {
        name: "score",
        label: "Reward",
        unit: "pts",
        range: [0, 1],
        higherIsBetter: false,
        primary: false,
      },
      { name: "resolved", label: "Resolved", unit: "%", higherIsBetter: true, primary: true },
    ]);
    expect(ms.map((m) => [m.name, m.primary])).toEqual([
      ["score", false],
      ["cost", false],
      ["resolved", true],
    ]);
    expect(ms[0]).toMatchObject({
      label: "Reward",
      unit: "pts",
      range: [0, 100],
      higherIsBetter: true,
    });
    expect(resolveMetrics(ms)).toEqual(ms);
    expect(primaryMetric(ms).name).toBe("resolved");
  });

  it("reads score as percent of max and adapter metrics by name", () => {
    expect(metricValue(o(1), "score")).toBe(25);
    expect(metricValue(o(null), "score")).toBeNull();
    expect(metricValue(o(1, { cost: 0.5 }), "cost")).toBe(0.5);
    expect(metricValue(o(1), "cost")).toBeNull();
    expect(metricValue(null, "score")).toBeNull();
  });

  it("averages seeds per task first, clusters the SE by task and pairs differences", () => {
    const a = taskMeans(
      [
        { task: "t1", outcome: o(4) },
        { task: "t1", outcome: o(0) },
        { task: "t1", outcome: o(4) },
        { task: "t2", outcome: o(0) },
        { task: "t3", outcome: o(null) },
      ],
      "score",
    );
    expect([...a]).toEqual([
      ["t1", { mean: 200 / 3, n: 3 }],
      ["t2", { mean: 0, n: 1 }],
    ]);
    // Two tasks, not four trials: mean of task means, SE = sd / sqrt(2).
    const s = aggregate(a);
    expect(s).toMatchObject({ tasks: 2, trials: 4 });
    expect(s?.mean).toBeCloseTo(100 / 3);
    expect(s?.se).toBeCloseTo(100 / 3);
    expect(s?.ci?.[0]).toBeCloseTo(100 / 3 - 1.959964 * (100 / 3));
    expect(aggregate(a, new Set(["t2"]))).toMatchObject({ mean: 0, se: null, ci: null });
    expect(aggregate(new Map())).toBeNull();

    const base = new Map([
      ["t1", { mean: 10 }],
      ["t2", { mean: 20 }],
      ["t3", { mean: 30 }],
    ]);
    const better = new Map([
      ["t1", { mean: 20 }],
      ["t2", { mean: 31 }],
      ["t4", { mean: 99 }],
    ]);
    const d = pairedDiff(base, better);
    expect(d).toMatchObject({ mean: 10.5, tasks: 2 });
    expect(d?.se).toBeCloseTo(0.5);
    expect(verdict(d, SCORE_METRIC)).toBe(1);
    expect(verdict(d, { ...SCORE_METRIC, higherIsBetter: false })).toBe(-1);
    expect(
      verdict(
        pairedDiff(
          base,
          new Map([
            ["t1", { mean: 0 }],
            ["t2", { mean: 40 }],
          ]),
        ),
        SCORE_METRIC,
      ),
    ).toBe(0);
  });

  it("formats values with units and places them in their range", () => {
    expect(fmtMetric(72.456, SCORE_METRIC)).toBe("72.5%");
    expect(fmtMetric(3.2, SCORE_METRIC, true)).toBe("+3.2 pt");
    expect(fmtMetric(48.25, { ...SCORE_METRIC, unit: "pts" })).toBe("48.3 pts");
    expect(fmtMetric(1.2345, { ...SCORE_METRIC, unit: "$" })).toBe("$1.23");
    expect(fmtMetric(0.12345, { ...SCORE_METRIC, unit: undefined })).toBe("0.123");
    expect(fmtMetric(null, SCORE_METRIC)).toBe("—");
    expect(fmtCi({ mean: 50, se: 1, ci: [46.8, 53.2], tasks: 3, trials: 3 }, SCORE_METRIC)).toBe(
      "±3.2",
    );
    expect(fmtCi(null, SCORE_METRIC)).toBe("");
    expect(goodness(25, SCORE_METRIC)).toBe(0.25);
    expect(goodness(25, { ...SCORE_METRIC, higherIsBetter: false })).toBe(0.75);
    expect(goodness(25, { ...SCORE_METRIC, range: undefined })).toBeNull();
  });

  it("validates adapter declarations and values", () => {
    const tasks = { tasks: [] };
    expect(AdapterTasksResponse.parse(tasks).metrics).toEqual([]);
    const m = { name: "cost", label: "Cost" };
    expect(AdapterTasksResponse.parse({ ...tasks, metrics: [m] }).metrics[0]).toMatchObject({
      higherIsBetter: true,
      primary: false,
    });
    expect(AdapterTasksResponse.safeParse({ ...tasks, metrics: [m, m] }).success).toBe(false);
    expect(
      AdapterTasksResponse.safeParse({
        ...tasks,
        metrics: [
          { ...m, primary: true },
          { name: "b", label: "B", primary: true },
        ],
      }).success,
    ).toBe(false);
    expect(
      AdapterTasksResponse.safeParse({ ...tasks, metrics: [{ name: "Bad name", label: "x" }] })
        .success,
    ).toBe(false);
    expect(ScoreResult.parse({ score: 1, metrics: { a: 1, b: null } }).metrics).toEqual({ a: 1 });
    expect(ScoreResult.parse({ score: 1 }).metrics).toBeUndefined();
  });
});
