# Project Status

Updated at: 2026-09-15T18:55:03+08:00

Basis: This task-branch version proposes the state after `feat/resource-management` and its stacked
`feat/agent-codex` parent are integrated. The branch ultimately descends from the unmerged
`docs/s1-plan` commit 67958a0 and main baseline 0a4a05a.

Current stage: S1 in progress after integration of the Agent and local resource vertical slices.

## Stage overview

| Stage | Status | Current conclusion |
| --- | --- | --- |
| S0 - repository foundation | accepted | Functional package layout, locked installation, checks, tests and Python/Web builds validated in an independent clean directory. |
| S1 - contracts and task examples | in_progress | Agent contracts and three adapters plus resource request/observation/lease contracts exist; cross-module lifecycle contracts, shared fakes and task examples remain. |
| S2 - complete single-node workflows | not_started | No working research or benchmark execution path. |
| S3 - two-node execution and failure handling | not_started | No verified Ray dispatch or resource recovery. |
| S4 - frontend and batch evaluation | not_started | A Web starting page builds; business console and batch workflows are absent. |

## Available outcomes

- [Agent module design](architecture/agent-module.md) defines the first public Agent boundary, provider registry and host/container responsibility split.
- Python package discovers Codex, Claude Code and DSH, prepares isolated file configuration, creates provider-specific host/container launch plans and normalizes JSONL events.
- The CLI supports provider-selected `agent doctor` and `agent setup`, including aliases. A shared fixed-version Node Agent image recipe replaces the Codex-only recipe.
- [Resource management design](architecture/resource-management.md) defines YAML admission, host monitoring, Docker enforcement, Ray scheduling and secure multi-node bootstrap boundaries.
- Python code strictly parses versioned resource YAML, observes Linux CPU/memory and NVIDIA GPUs, and grants concurrency-safe single-node leases with distinct waiting and unsatisfiable outcomes.
- The CLI validates requests and reads host snapshots. This host returned 80 logical CPUs, about 251 GiB physical memory and four RTX 3090 GPUs; an in-memory one-GPU lease/release smoke passed without starting a job.
- React/TypeScript Web starter, uv/pnpm locks, Make commands and all static checks remain valid; 66 deterministic tests, Python distributions, dependency-aware isolated wheel smoke and Web production build pass.
- CI configuration, contributor guidance, review routing, PR template, synchronized agent rules and documentation checks are implemented.
- [Environment and operations Q&A](architecture/environment-operations-qa.md) retains design guidance for automation, clusters, traces and both execution modes; it is not runtime evidence.

## Main gaps

- Hosted CI has not run for this branch; GitHub main protection and reviewer access remain unverified. S0 acceptance is local engineering evidence, not hosted integration evidence.
- No Environment executor consumes Agent launch plans yet; no model request or real Agent task has been validated.
- This host's Claude Code login has no copyable `.credentials.json`, so Claude container authentication needs explicit secret injection or file credentials. DSH has no generic side-effect-free authentication probe and its structured headless protocol is pinned to a preview release.
- Run/Attempt lifecycle contracts, Tasks, durable resource leases/queues, Records, evaluation, cancellation and shared fakes remain absent.
- Docker limits and GPU mapping are designed but no Environment Docker adapter applies them yet. Ray is not installed or started, and multi-node authentication/deployment remains unvalidated.
- Fine-grained public/private import checks still need to accompany the remaining S1 contracts.
- Actual four-person identities/review assignments and license selection remain open.

## Next priorities

1. Review and integrate the stacked Agent and resource slices after resolving their `docs/s1-plan` dependency.
2. Implement the Environment Docker adapter that applies a lease's CPU, memory and GPU UUID limits and verifies cleanup before release.
3. Persist queue/lease state through Run/Records and validate the single-node workflow before adding the Ray backend and two-node bootstrap.

## Project-level blockers

The provider-selected container end-to-end path is blocked on the Environment runtime. Real Ray
validation additionally needs an authorized second node and private network. Publishing and hosting
configuration remain with the maintainer.

## Related records

- [S0 implementation and validation](changes/20260915-s0-foundation-b7e492.md).
- [S0 scope and acceptance](development/s0-engineering-foundation.md).
- [Development sequence](development/development-sequence.md) and [four-person allocation](development/four-person-collaboration.md).
- [Replaceable command-Agent implementation record](changes/20260915-agent-codex-4d2f1a.md).
- [Resource management implementation record](changes/20260915-resource-management-8c31e7.md).
