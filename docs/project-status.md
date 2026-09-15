# Project Status

Updated at: 2026-09-15T16:57:57+08:00

Basis: This task-branch version proposes the state after `feat/agent-codex` is integrated. The
branch is based on the unmerged `docs/s1-plan` commit 67958a0 and main baseline 0a4a05a.

Current stage: S1 in progress after integration of this Agent vertical slice.

## Stage overview

| Stage | Status | Current conclusion |
| --- | --- | --- |
| S0 - repository foundation | accepted | Functional package layout, locked installation, checks, tests and Python/Web builds validated in an independent clean directory. |
| S1 - contracts and task examples | in_progress | Agent discovery and command-plan contracts plus a Codex adapter exist; cross-module lifecycle contracts, shared fakes and task examples remain. |
| S2 - complete single-node workflows | not_started | No working research or benchmark execution path. |
| S3 - two-node execution and failure handling | not_started | No verified Ray dispatch or resource recovery. |
| S4 - frontend and batch evaluation | not_started | A Web starting page builds; business console and batch workflows are absent. |

## Available outcomes

- [Agent module design](architecture/agent-module.md) defines the first public Agent boundary and its host/container responsibility split.
- Python package discovers Codex, checks login without exposing identity, prepares isolated file credentials, creates host/container launch plans and normalizes JSONL events.
- The CLI supports `agent doctor codex` and idempotent `agent setup codex`; a pinned Codex 0.154.0 container recipe is present.
- React/TypeScript Web starter, uv/pnpm locks, Make commands and all static checks remain valid; 29 deterministic tests, the wheel and Web build pass.
- CI configuration, contributor guidance, review routing, PR template, synchronized agent rules and documentation checks are implemented.
- [Environment and operations Q&A](architecture/environment-operations-qa.md) retains design guidance for automation, clusters, traces and both execution modes; it is not runtime evidence.

## Main gaps

- Hosted CI has not run for this branch; GitHub main protection and reviewer access remain unverified. S0 acceptance is local engineering evidence, not hosted integration evidence.
- No Environment executor consumes Agent launch plans yet; no model request or real Codex-in-Docker task has been validated.
- Run/Attempt lifecycle contracts, Tasks, Resources, durable Records, evaluation, cancellation and shared fakes remain absent.
- Fine-grained public/private import checks still need to accompany the remaining S1 contracts.
- Actual four-person identities/review assignments and license selection remain open.

## Next priorities

1. Review the Agent contract and integrate this branch after resolving its `docs/s1-plan` dependency.
2. Implement the Environment local-process and Docker execution port that consumes `AgentLaunchPlan`.
3. Add Run/Records integration, then validate one paid host run and one task-owned Docker run with explicit budgets and cleanup evidence.

## Project-level blockers

The Codex container end-to-end path is blocked on the Environment runtime. Publishing and hosting
configuration remain with the maintainer.

## Related records

- [S0 implementation and validation](changes/20260915-s0-foundation-b7e492.md).
- [S0 scope and acceptance](development/s0-engineering-foundation.md).
- [Development sequence](development/development-sequence.md) and [four-person allocation](development/four-person-collaboration.md).
- [Codex Agent implementation record](changes/20260915-agent-codex-4d2f1a.md).
