# Project Status

Updated at: 2026-09-15T20:54:54+08:00

Basis: This task branch proposes Tasks and local Run/Environment on main baseline `99dbd1a` and
the task-design commit `8b95188`. Agent and local Resources are integrated in that main baseline;
the Tasks and Run/Environment additions below remain task-branch outcomes until merged.
This branch builds on Tasks commit 8f09c14; it does not claim integration into main.

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
- Task-branch outcome: [Tasks APIs](reference/tasks.md) parse versioned manifests, project solver views, fingerprint and copy allowed materials, review/revise research drafts, check resource bounds and index native-prepared workspaces. An explicit evaluator registry includes a small platform-only fixture scorer.
- The CLI validates requests and reads host snapshots. This host returned 80 logical CPUs, about 251 GiB physical memory and four RTX 3090 GPUs; an in-memory one-GPU lease/release smoke passed without starting a job.
- Task-branch outcome: local Run, Docker Environment and controller records support solver-only research and clean evaluator containers; see [execution reference](reference/run-environment.md).
- React/TypeScript Web starter, uv/pnpm locks, Make commands and all static checks remain valid; 104 deterministic tests, Python distributions, dependency-aware isolated wheel smoke and Web production build pass.
- CI configuration, contributor guidance, review routing, PR template, synchronized agent rules and documentation checks are implemented.
- [Environment and operations Q&A](architecture/environment-operations-qa.md) retains design guidance for automation, clusters, traces and both execution modes; it is not runtime evidence.

## Main gaps

- Hosted CI has not run for this branch; GitHub main protection and reviewer access remain unverified. S0 acceptance is local engineering evidence, not hosted integration evidence.
- The local Run/Environment API consumes container Agent launch plans, with solver-only and isolated evaluation modes. Real model requests and real Agent tasks remain unvalidated.
- This host's Claude Code login has no copyable `.credentials.json`, so Claude container authentication needs explicit secret injection or file credentials. DSH has no generic side-effect-free authentication probe and its structured headless protocol is pinned to a preview release.
- Task authoring model orchestration, real tool injection and native benchmark evaluator equivalence remain incomplete; indexed imports are not compatibility certification. Durable leases/queues, crash recovery, distributed Worker execution and public Run gateways remain absent.
- Docker Environment applies CPU/memory and GPU UUID settings; CPU-only execution and cleanup are validated. GPU workload enforcement, Ray and multi-node authentication/deployment remain unvalidated.
- Fine-grained public/private import checks still need to accompany the remaining S1 contracts.
- Actual four-person identities/review assignments and license selection remain open.

## Next priorities

1. Complete Tasks integration: authoring orchestration, ToolBinding and native benchmark equivalence, using the task-branch foundation.
2. Connect the local Run API to CLI/HTTP and validate a real Agent task with an explicit budget.
3. Persist queue/lease state through Run/Records and validate the single-node workflow before adding the Ray backend and two-node bootstrap.

## Project-level blockers

Real Agent validation still needs a configured image, credentials and a model budget. Real Ray
validation needs an authorized second node and private network. Publishing and hosting
configuration remain with the maintainer.

## Related records

- [S0 implementation and validation](changes/20260915-s0-foundation-b7e492.md).
- [S0 scope and acceptance](development/s0-engineering-foundation.md).
- [Development sequence](development/development-sequence.md) and [four-person allocation](development/four-person-collaboration.md).
- [Replaceable command-Agent implementation record](changes/20260915-agent-codex-4d2f1a.md).
- [Resource management implementation record](changes/20260915-resource-management-8c31e7.md).
- [Tasks implementation progress](changes/20260915-task-implementation-a71e40.md).
- [Run/Environment implementation](changes/20260915-run-environment-91c2ae.md).
