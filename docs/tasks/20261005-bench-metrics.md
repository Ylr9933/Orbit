# Bench metrics declared by adapters
branch: feat/bench-metrics · status: completed · updated: 2026-10-05

## Goal
Plan A: adapters declare metrics with their tasks and report values per trial; Orbit aggregates valid trials
per metric and shows a primary metric plus the others in jobs, compare, trial pages, CLI and run metrics.
Statistics follow common evaluation practice (Anthropic "A statistical approach to model evaluations",
Inspect `stderr(cluster=)`, Terminal-Bench resolution rate ± 95% CI, HAL multi-metric leaderboards).

Replaces a first attempt (kept on `review/gemini-bench-metrics`) that mixed percent and raw values (Harbor ×100,
ASI raw `final_score` labelled %), duplicated value extraction in daemon and Web, compared `cells` of a
different unit than the selected metric, took the SE over trials, and left the CLI unchanged.

## Changes
- `contracts.MetricSpec`; `AdapterTasksResponse.metrics`, `ScoreResult.metrics`, `Outcome.metrics`,
  `BenchJob.metrics` (resolved at submit); `MethodSummary.metrics` and `BenchCompare.{metrics, rows.values,
  stats}` replace `meanPct` / `cells` / `means` / `pairedTasks`.
- `contracts/metrics.ts` (no imports, exported as `@zjunlp/orbit/metrics`): built-in `score`, declaration
  resolution, values, per-task → over-task means, task-clustered SE / 95% CI, paired differences, formatting.
  Used by bench service, CLI and Web; boundaries allow it in the Web bundle.
- Verify runs get a `metrics.jsonl` line `bench/<name>` per metric.
- Harbor: primary `resolved` (reward ≥ 1) + Reward; ASI: `score` + `fullMarks`; RCB example: `score` in pts
  with reference 50, `matched`, `judgeSpread` (sample std).
- CLI: `bench jobs/show` show metrics with CIs; `bench compare --metric` with paired Δ.
- Web: shared `BenchMetrics.tsx` (metric switch on `.seg` in `?metric=`, range/direction heat cells,
  mean ± CI bars with reference line); job cards with reference gap and other metrics, ranking, compare Δ
  with significance, trial metric line, run-list job rows.
- Docs: design §3/§7, bench adapter guide, RCB README, status.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | orbit 108 passed / 3 skipped; web 9 passed; build ok |
| New tests | working tree | passed | `test/metrics.test.ts`; daemon test with a metric-declaring external adapter and run metrics |
| Real Agent job with several metrics in the Web | — | not_run | needs a real RCB / TB-Science job |

## Next / open issues
- Look at the Web pages with a real multi-metric job (RCB) and adjust layout if needed.
- Cost / tokens per trial (HAL-style accuracy vs cost) would need measured usage as a metric; not done.
