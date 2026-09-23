---
record_version: 1
task_id: "20260923-benchmark-campaign-bm06-7a31d9"
title: "BM06 bounded outer benchmark optimization campaign"
branch: "feat/benchmark-campaign-bm06"
base_commit: "c51d845d528919786c11d78bf863c293fdd8481f"
work_status: completed
updated_at: "2026-09-23T10:52:55+08:00"
pull_request: null
---

## Goal and acceptance

- Freeze a baseline and successor Candidate with parent, change and feedback lineage; prohibit
  changes outside an operator-authorized scope and preserve the benchmark protocol.
- Allow the optimizer to see only explicitly released after-trial feedback; retain all trials,
  failed attempts and comparison evidence rather than selecting only the best score.
- Enforce cumulative trial and wall-time budgets, deterministic submission IDs, restart-safe
  state, and explicit stop/selection rules. Demonstrate two candidates using allowed feedback.

## Changes

- Added versioned `CampaignPolicy`, immutable candidate lineage and allowed-change validation;
  the campaign stores only released numeric feedback, chosen score, outcomes and Run references.
- Added durable campaign create/propose/submit/status/stop through the benchmark CLI. Deterministic
  operation IDs recover lost replies; BM05-B budget groups enforce cumulative wall-time admission.
- Reused the existing adapter/source/invocation/capability preflight on every candidate submit.
  Fixed benchmark CLI dispatch so BM05-B `capacity` and `worker` reach their existing handlers.
- Added user and maintainer guides plus a proposed project-status update.

## Decisions

- Build on BM05-B's immutable PreparedExecution and durable Run/Records rather than duplicating
  the benchmark runner or introducing a benchmark-specific core branch.
- Require an explicit optimizer `FeedbackRule` before campaign creation. The four reference
  adapters currently lack that permission, so no admin/private metric is promoted automatically.
- Candidate modification is limited to named request parameters and selected CandidateRef fields;
  suite, source, units, phases, retry, judge and native budget remain frozen. Final selection uses
  a declared development metric and does not imply official score or submission eligibility.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Initial branch and plan inspection | `c51d845d528919786c11d78bf863c293fdd8481f` | passed | Clean BM05-B branch; BM06 branch created from it. |
| `uv run --locked pytest -q tests/unit/projects/test_benchmark_campaign.py tests/unit/benchmarks/test_execution.py` | BM06 workspace | passed | 22 tests: two synthetic candidates, feedback isolation, protocol rejection, improvement stop, lost reply and CLI composition. |
| `uv run --locked lint-imports --no-cache && uv run --locked mypy` | BM06 workspace after fixes | passed | 145 source files; dependency direction kept. |
| `uv run --locked pytest -q tests/unit/benchmarks/test_execution.py::test_benchmark_capacity_command_persists_and_rejects_unknown_fields` | BM06 workspace after CLI routing test | passed | One top-level capacity dispatch test. |
| `make verify` | BM06 workspace before final view restriction | passed | Import graph, Ruff, mypy, Markdown links, 395 unit/contract tests, wheel and Web build; 33 integration/E2E excluded by repository target. |
| `uv run --locked pytest -q tests/unit/projects/test_benchmark_campaign.py tests/unit/benchmarks/test_execution.py` | BM06 final code snapshot | passed | 22 tests after removing private outcome fields from Campaign view. |
| `uv run --locked ruff check src/agent_infra/projects/benchmark_campaign.py tests/unit/projects/test_benchmark_campaign.py && uv run --locked ruff format --check src/agent_infra/projects/benchmark_campaign.py tests/unit/projects/test_benchmark_campaign.py && uv run --locked mypy && uv run --locked python scripts/ci/check_repository.py` | BM06 final code/docs snapshot | passed | Formatting, types and document links after final restriction. |
| Real model, GPU, native/official benchmark score | Not in authorized acceptance scope | not_run | Synthetic tests do not establish benchmark or model equivalence. |

## Open items and blockers

- None within the generic BM06 scope. The four reference adapters still need protocol-approved
  optimizer feedback before real outer optimization, and single-admin CLI access itself does not
  isolate an optimizer from other administrator commands.

## Next steps

- Commit this branch for review. Integrate BM05-B before BM06; then enable a compliant public
  development metric in one adapter and perform a bounded real two-candidate trial separately.

## Compatibility and rollback

- No existing benchmark plan/Run schema should change. Campaign state is an additive namespace;
  retain it with BM05-B control, leases and Records when rolling back or migrating.
- CLI additions do not change existing run IDs or reference-adapter behavior. BM06 branches from
  unmerged BM05-B commit `c51d845`, so integrate BM05-B first.
