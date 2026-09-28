---
record_version: 1
task_id: "20260928-asi-b3-review-e91c7a"
title: "Evidence-based review of the 60-task ASI b3 batch"
branch: "analysis/asi-b3-review-20260928"
base_commit: "54165f5aa691b38a284c6a35fa71fc2b326e31c0"
work_status: completed
updated_at: "2026-09-28T08:38:46.189312+00:00"
pull_request: null
---

## Goal and acceptance

- Audit all 60 saved ASI b3 public-instance scores and artifact coverage; inspect low/middle/high submissions and native trajectories in depth.
- Produce evidence-linked findings, distinguish observations from causal hypotheses, and propose bounded follow-up experiments without running them.
- Record concrete friction using existing Infra interfaces before further optimization. No model/Docker/GPU execution, rescoring, runtime mutation, frontend changes or deployment.

## Changes

- Completed a full-cohort audit and 20 purposively selected case reviews, including all five zero-score tasks and five high-score controls. Reviewed scoring-error paths, key submitted implementations and trajectory validation steps; did not claim line-by-line scientific verification of every submission.
- The ignored runtime directory `benchmark/asibench/review-b3-20260928/` contains `REPORT.md`, `CASE_STUDIES.md`, `ALL_TASKS.md`, 60 per-task evidence indexes, CSV/JSON tables, plots, six reproduction scripts, source excerpts/hashes and validation results. Raw artifacts remain outside Git.
- Updated the relevant project overview conclusions: a persisted numeric score is not sufficient evidence of healthy evaluation or successful Agent termination. Stage acceptance is unchanged.

### Principal findings

| Finding | Evidence and interpretation |
| --- | --- |
| Stored local mean 35.43277818088395; median 19.12277543068594 | 5 zero, 26 above zero/below 20, 15 in [20,60), 11 in [60,100), 3 at 100. One public instance per task, not an official aggregate. |
| 12 tasks / 13 nested judge-unavailable nodes | Saved parameter-compatibility errors; one hard gate blocks CMOS scientific scoring, another error is nested within NNLS. Do not impute full credit or predict a score gain. |
| 7 tasks with scorer input/runtime dependency errors | Five inputs exist in instance directories but not prediction directories; MPSC cannot find `uv` in its scorer runtime; HMC references absent `generate_gt.py`. Independent numerical failures may coexist. |
| 19 distinct tasks contain one of those evaluation anomalies | The other 41 are not certified error-free. All 60 top-level numeric scores match summary, Workspace, native-result and BenchFlow projections. |
| 13 native timeout labels: 12 completed turns, one quota failure | Native adapter searches `"timed out"` anywhere in the combined log. All 13 have model-list refresh timeout messages; 12 end with `turn.completed`, one ends with explicit usage-limit `turn.failed`. TSP has a separate scorer-side solver timeout. |
| All native per-instance `final_score` fields are produce-only placeholders | The `unscored_submission` zero values must not be confused with separate BenchFlow scores. |
| Ag output-contract ambiguity | Recomputed 0.416482923 cross-file difference from saved CSVs. Public notes specify peak bands but omit the central off-resonance band used by the scorer. Do not secretly inject evaluator-only definitions into candidate prompts. |
| Method validation often misses the scientific target | ICP confidence all >0.99 despite poor degeneracy scores; Gillespie public fit near full credit but intervention score 0/60; scRNA clustering/markers outperform pseudotime/GRN. These are observations, not measured causal effects. |
| Positive controls | Attention uses public probes and derivative checks; RNEA compares conventions and temporal calibration; photosynthesis checks coupled equations. LBM scores highly while honestly retaining two unconverged cases. |

## Decisions

- Used a separate clone at `/tmp/infra-asi-review-20260928` because current filesystem permissions allow source/runtime writes and `/tmp`, but protect original Git metadata and sibling directories. The original clean branch was preserved.
- Used the existing Workspace/Evidence/Records interfaces to select and extract archives, with only task-owned temporary registration metadata. Did not create a second execution or scoring implementation.
- Preserved the [consolidation history](20260928-asi-b3-consolidate-retry-8c7d4e.md): causal-attention is a later successful retry, not a first-pass success. Do not infer complete original attempt cost from the consolidated snapshot.
- Prioritize evaluator correctness and status semantics before Agent tuning or visual redesign. Proposed next experiments use immutable submissions for re-evaluation and new development instances for strategy comparisons; no experiments or optimizations were performed.
- Full raw stdout is archived for all tasks; 37 bounded trajectory previews are truncated. Used full normalized trajectories (2,590 steps) and original JSONL. Missing step timestamps prevent honest per-step timing estimates.
- Reported actual interface friction without claiming a controlled no-Infra productivity comparison: nested error interpretation and contradictory state semantics took the most reasoning; file retrieval itself was quick. One scratch extractor failed on null usage, then was corrected and rerun successfully.

## Validation

Evidence snapshot: batch digest `sha256:6b3a90825313a303627724bbcee15515ca86c1547f369e0f12b59e95d0c39086`; Infra code `54165f5`.
Runtime review manifest SHA-256: `5c50f964162954fe4513c6f0d0e4e4070109947a468b5659b66831337daf12fc`.
Full report SHA-256: `5aa67f93c0a519229629ae87141eda846930e48a0c363f35a83fe0d2bb67991a`.

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Repository and task history inspection | 54165f5 | passed | Original branch clean; separate clone/analysis branch. |
| `extract.py` through Workspace and Evidence | Batch digest above | passed | 60 score projections agree; initial null-usage handling fixed before successful full rerun. Core read/export about 1.22 s on warm local storage, not a benchmark. |
| `enrich.py` with Records-backed artifact reads | Same immutable artifact manifests | passed | All 1,192 members / 45,580,888 bytes hash-verified; full extraction/hash/write about 2.30 s, not a general latency claim. |
| `inspect_outputs.py` | Stored outputs and public inputs | passed | Independently recomputed Ag mismatch and ICP confidence range; verified five missing scorer input paths and 59 successful terminal turns / one quota failure. Never imported submitted code. |
| Manual source and stratified case audit | 9 hashed source/spec files and 20 case evidence sets | passed | Supports failure-path and method observations. No alternative solver or scorer was run; hypotheses remain untested. |
| `plot.py` and visual inspection | 60 stored scores | passed | PNG/SVG distribution and anomaly overlay, clearly descriptive/non-official. |
| `validate.py` | Review manifest above | passed | 60 unique task/Run identities, 20 case references, 807 generated report links, 1,192 hashes, six script syntax checks. All 65 original business files unchanged. |
| `python3 scripts/ci/check_repository.py`; `git diff --check` | Final documentation changes | passed | Policy parity and repository Markdown links checked; no source/API change. |
| New model execution, judge calls, Docker/GPU, full application test suite | None | not_run | Not part of this offline analysis. No corrected score or scientific causal improvement claimed. |

## Open items and blockers

- None for the offline review. Evaluation anomalies, state semantics and future strategy hypotheses remain separate follow-up work.
- Re-evaluation requiring a judge has model-budget implications; an unchanged-output controlled protocol should be prepared before running it. Public scorer dependencies/ambiguous specifications require confirmation, not arbitrary changes to hidden references.

## Next steps

- Review the concrete findings and prioritize evaluator health and terminal-state fixes before tuning or Web redesign. No new run, push or merge performed.

## Compatibility and rollback

- No product/API/data-schema changes. Original runtime scores, submissions and databases are unchanged. Remove the new ignored review directory to discard derived analysis; revert this documentation checkpoint to restore the prior overview.
- Reports and raw evidence are local runtime artifacts, not included in the documentation commit. Their reproducibility scripts, manifest and concise versioned record make this distinction explicit.
