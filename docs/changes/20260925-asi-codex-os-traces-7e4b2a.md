---
record_version: 1
task_id: "20260925-asi-codex-os-traces-7e4b2a"
title: "Run ASI-Bench with native Codex OS sandbox and preserve its evidence"
branch: "feat/asi-codex-os-traces"
base_commit: "361a958b53c25cac6f406d346f5fa34c09943d01"
work_status: completed
updated_at: "2026-09-25T16:54:00+08:00"
pull_request: null
---

## Goal and acceptance

- After syncing both remotes, add an explicitly selectable, pinned ASI-Bench Codex CLI / Docker OS profile without regressing the existing fixture profile.
- Preserve native stdout JSONL, normalized trajectory, stderr and available call evidence with capture status, and link the native instance and prompt level to the platform Run/Attempt.
- Expose a bounded, authenticated per-run trajectory view in the Web benchmark page; keep private material out of the public summary.
- Validate contracts and an actual scoped Codex Docker trial only within the user's approved resource/model budget.

## Changes

- Added a separate `asi-bench-codex-os` entry point with an explicit native Codex/Docker OS profile and 4 CPU/8 GiB/zero GPU request; kept the fixture entry point and its request serialization stable.
- Added bounded native sidecar capture, coverage index, Codex session/turn evidence, Docker identity/limit/usage sampling and task-labeled container cleanup.
- Added authenticated Run/Attempt-scoped trajectory pagination and a concise Web view; updated ASI implementation and operations guidance.
- Updated the concise project overview with this validated capability and its remaining public-single-instance/official-submission limits.

## Decisions

- Existing fixture plans and state must remain readable; native ASI-Bench owns prompt, sandbox and scoring semantics.
- ASI-Bench's pinned OS sandbox currently defaults to 4 CPU / 8 GiB. The requested real trial uses one local public instance, no GPU, a 300-second native timeout and `gpt-5.6-sol`.
- The local loopback proxy needs host networking for both ASI's Docker image build and the Agent container; the task's Docker CLI shim adds build `--network host` only for this explicitly selected mode.
- Pre-implementation Git integration: all local branches already merged; pushed `main` at `361a958` to both `origin` and `zjunlpgit` and verified both remote heads.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `git branch --no-merged main`, `git push origin main`, `git push zjunlpgit main`, remote HEAD checks | `361a958` | passed | No unmerged local branches; both remote `main` refs at the same SHA. |
| `make verify` | Task branch workspace before the second real trial | passed | 399 non-integration tests, lint, type check, repository checks and Web build. |
| Isolated adapter tests and authenticated Web trajectory test | Task branch workspace before second real trial | passed | 16 adapter tests and direct/HTTP Records projection test. |
| `benchmark inspect/plan/check/prepare` in isolated wheel environment | Task branch workspace with pinned ASI checkout | passed | Exact Codex OS declaration compatible; offline check is not runtime attestation. |
| First real ASI Codex OS trial (`f5b07c90…`) | Task branch workspace before loopback build fix | failed | Docker image build could not reach host's loopback proxy, so Codex never started. Failure result and outer log archived; lease released. |
| Second real ASI Codex OS trial and `benchmark reconcile` | Task branch workspace after loopback build fix, run `79737b0fd1f3492fb77e2248daab9c19` / attempt `attempt_51b09f2ae1ed4827970b40d9aea88d0e` | passed | Native `codex_cli` ran in Docker OS with `gpt-5.6-sol`; `execution=completed`, `evaluation=scored`, `protocol=valid`, public local score 76.3635, `official_score=null`. Records artifact `artifact_0ea0893c323f4b98b179563a4c5b4445` has complete JSONL (16,070 bytes), stderr, derived 20-step trajectory, native result/prediction, and 95 Docker usage samples. Container ID and 4 CPU/8 GiB limits attested; cleanup complete, no labeled container remains, lease released. |
| `BenchmarkConsole.trajectory` against the real Records artifact | Same live run, after reconcile | passed | Run/Attempt, native instance, `b1`, Codex session `01a0d7c0-d4c8-74b0-9d29-9061527cb9c8`, tool call/result steps, Docker ID and sample count page correctly. |
| Final adapter tests, lint/format, repository links and Web checks | Final task-branch workspace | passed | 17 adapter tests, changed-file Ruff, policy/link checker, Biome and TypeScript. |

## Open items and blockers

- None for this public single-instance scope. Complete-suite and official seed42 submission remain separate work.

## Next steps

- None for the authorized implementation; review and merge this task branch through the repository workflow.

## Compatibility and rollback

- Existing fixture entry point, request serialization and frozen plans remain stable. The new profile requests 4 CPU/8 GiB and requires Docker/auth plus a reachable network or proxy. Removing the new entry point, Codex backend and Web projection rolls back behavior; existing Records evidence remains immutable. The ASI pinned runner currently lacks a separate `model_calls_file`, so call evidence comes from the archived JSONL and is labeled accordingly.
