# Web: bench jobs and trials in the run list, trial page, run names, deletion
branch: refactor/ts-rewrite · base `d131e03` · status: completed · updated: 2026-10-04T14:10:00+08:00

## Goal

The run list mixed bench jobs with experiment groups (`bench-<id>`), trials were only visible in the
Bench matrix, unnamed runs showed their full command, and records could only grow. Make jobs and
trials first-class in the Web UI, name unnamed runs from their command by a fixed rule, ask Agents to
name runs, and allow deleting finished runs and jobs behind a typed confirmation.

## Changes

- Runs page: bench job rows (benchmark, trial progress, method means) expanding into trial rows
  (solve → verify states, score, evaluation, first issue); filter All / Experiments / Benchmarks;
  search also matches job names, benchmark and methods.
- Trial page `/bench/<job>/trials/<trial>`: outcome, issues, solve → verify timeline with measured
  use; Report (Markdown with figures from the same run; a small React renderer, no HTML, no remote
  images), Grader (JSON outputs; `items` tables with criterion, weight, score, reasoning), Agent
  session. Matrix cells and issue rows link to it. Scores rounded for display.
- Run names: `contracts/naming.ts` (`autoRunName`, `runDisplayName`), shared by CLI and Web
  (`@zjunlp/orbit/naming`, allowed by the boundary check). Skill asks for short `-n` / `-g` names.
- Deletion: `RunService.delete` (finished, cleaned up, not a trial run, mirroring over; all checked
  first; records, events, leases, directory; root-owned files emptied from a throwaway container),
  `BenchService.deleteJob` (not running: trials, runs, staging). API `POST runs/delete`,
  `DELETE bench/jobs/:id`, SSE `deleted`. CLI `orbit rm <id>... | -g`, `orbit bench rm-job` with
  typed confirmation (`--yes` without a terminal). Web: delete selected runs, delete run, delete job,
  all through a GitHub-style dialog (type the id / group / job id).
- Docs: design §3/§5, README (en/zh), skill.

## Validation

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree on `d131e03` | passed | orbit 97 + 3 skipped, web 8 |
| New tests | same | passed | naming rule cases; delete refuses active / trial runs, removes records and directories, deletes a job with its runs; report path join and choice |
| Browser on a copy of the real `~/.orbit` (headless Chromium, port 7722) | same | passed | 3 job rows, trial rows on expand; Experiments hides jobs; trial page renders `report.md` with 10 figures; Grader shows 3 judged items; delete dialog disabled until the id is typed, run removed; no page errors |
| CLI on the copy | same | passed | without a terminal refuses unless `--yes`; wrong typed text deletes nothing; group name deletes; `bench rm-job --yes` removes job and 4 runs |
| Real `~/.orbit` | — | not_run | nothing deleted on the user's own records |

## Next / open issues

- No archive (hide without deleting); grader view understands `items` only.
