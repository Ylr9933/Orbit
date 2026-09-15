# Project Status

Updated at: 2026-09-15T17:33:37+08:00

Basis: This task-branch version proposes the state after `feat/agent-codex` is integrated. The
branch is based on the unmerged `docs/s1-plan` commit 67958a0 and main baseline 0a4a05a.

Current stage: S1 in progress after integration of this Agent vertical slice.

## Stage overview

| Stage | Status | Current conclusion |
| --- | --- | --- |
| S0 - repository foundation | accepted | Functional package layout, locked installation, checks, tests and Python/Web builds validated in an independent clean directory. |
| S1 - contracts and task examples | in_progress | Agent discovery and command-plan contracts plus Codex, Claude Code and DSH adapters exist; cross-module lifecycle contracts, shared fakes and task examples remain. |
| S2 - complete single-node workflows | not_started | No working research or benchmark execution path. |
| S3 - two-node execution and failure handling | not_started | No verified Ray dispatch or resource recovery. |
| S4 - frontend and batch evaluation | not_started | A Web starting page builds; business console and batch workflows are absent. |

## Available outcomes

- [Agent module design](architecture/agent-module.md) defines the first public Agent boundary, provider registry and host/container responsibility split.
- Python package discovers Codex, Claude Code and DSH, prepares isolated file configuration, creates provider-specific host/container launch plans and normalizes JSONL events.
- The CLI supports provider-selected `agent doctor` and `agent setup`, including aliases. A shared fixed-version Node Agent image recipe replaces the Codex-only recipe.
- React/TypeScript Web starter, uv/pnpm locks, Make commands and all static checks remain valid; 47 deterministic tests, Python distributions, isolated wheel smoke and Web production build pass.
- CI configuration, contributor guidance, review routing, PR template, synchronized agent rules and documentation checks are implemented.
- [Environment and operations Q&A](architecture/environment-operations-qa.md) retains design guidance for automation, clusters, traces and both execution modes; it is not runtime evidence.

## Main gaps

- Hosted CI has not run for this branch; GitHub main protection and reviewer access remain unverified. S0 acceptance is local engineering evidence, not hosted integration evidence.
- No Environment executor consumes Agent launch plans yet; no model request or real Agent task has been validated.
- This host's Claude Code login has no copyable `.credentials.json`, so Claude container authentication needs explicit secret injection or file credentials. DSH has no generic side-effect-free authentication probe and its structured headless protocol is pinned to a preview release.
- Run/Attempt lifecycle contracts, Tasks, Resources, durable Records, evaluation, cancellation and shared fakes remain absent.
- Fine-grained public/private import checks still need to accompany the remaining S1 contracts.
- Actual four-person identities/review assignments and license selection remain open.

## Next priorities

1. Review the three Agent adapters and integrate this branch after resolving its `docs/s1-plan` dependency.
2. Implement the Environment local-process and Docker execution port that consumes `AgentLaunchPlan`.
3. Add Run/Records integration, then validate provider-selected host and task-owned Docker runs with explicit budgets and cleanup evidence.

## Project-level blockers

The provider-selected container end-to-end path is blocked on the Environment runtime. Publishing
and hosting configuration remain with the maintainer.

## Related records

- [S0 implementation and validation](changes/20260915-s0-foundation-b7e492.md).
- [S0 scope and acceptance](development/s0-engineering-foundation.md).
- [Development sequence](development/development-sequence.md) and [four-person allocation](development/four-person-collaboration.md).
- [Replaceable command-Agent implementation record](changes/20260915-agent-codex-4d2f1a.md).
