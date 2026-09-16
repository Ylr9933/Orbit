# Project Status

Updated at: 2026-09-16T16:44:12+08:00

Basis: this Records feature branch is based on the local documentation baseline at `11bfad1`.
Agent, Resources, Tasks and the local Run/Environment slice come from the earlier `main` baseline;
the Records capabilities below are proposed branch outcomes until this branch is merged.

Current stage: S1 remains in progress, with an early S2 single-node Docker slice integrated.

## Stage overview

| Stage | Status | Current conclusion |
| --- | --- | --- |
| S0 - repository foundation | accepted | Functional package layout, locked installation, checks, tests and Python/Web builds validated in an independent clean directory. |
| S1 - contracts and task examples | in_progress | Agent, Resources, Tasks and Run/Environment contracts plus task examples exist; tool binding, native benchmark equivalence and remaining public boundaries are incomplete. |
| S2 - complete single-node workflows | in_progress | A CPU Docker path supports solver-only research and isolated fixture evaluation; real Agent, GPU and native benchmark validation remain. |
| S3 - two-node execution and failure handling | not_started | No verified Ray dispatch or resource recovery. |
| S4 - frontend and batch evaluation | not_started | A Web starting page builds; business console and batch workflows are absent. |

## Available outcomes

- [Agent module design](architecture/agent-module.md) defines the first public Agent boundary, provider registry and host/container responsibility split.
- Python package discovers Codex, Claude Code and DSH, prepares isolated file configuration, creates provider-specific host/container launch plans and normalizes JSONL events.
- The CLI supports provider-selected `agent doctor` and `agent setup`, including aliases. A shared fixed-version Node Agent image recipe replaces the Codex-only recipe.
- [Resource management design](architecture/resource-management.md) defines YAML admission, host monitoring, Docker enforcement, Ray scheduling and secure multi-node bootstrap boundaries.
- Python code strictly parses versioned resource YAML, observes Linux CPU/memory and NVIDIA GPUs, and grants concurrency-safe single-node leases with distinct waiting and unsatisfiable outcomes.
- [Tasks APIs](reference/tasks.md) parse versioned manifests, project solver views, fingerprint and copy allowed materials, review/revise research drafts, check resource bounds and index native-prepared workspaces. An explicit evaluator registry includes a small platform-only fixture scorer.
- The CLI validates requests and reads host snapshots. This host returned 80 logical CPUs, about 251 GiB physical memory and four RTX 3090 GPUs; an in-memory one-GPU lease/release smoke passed without starting a job.
- Local Run, Docker Environment and controller records support solver-only research and clean evaluator containers; see [execution reference](reference/run-environment.md).
- The Records feature branch replaces the controller journal with versioned Run/Attempt manifests, idempotent canonical events, SQLite WAL metadata, content-addressed streams and Artifacts, queries, Agent event normalization, evaluator-private records, Attempt trajectories and fixed JSONL exports; see [Records reference](reference/records.md).
- React/TypeScript Web starter, uv/pnpm locks, Make commands and all static checks remain valid; 111 deterministic non-E2E tests and seven real local Docker E2E cases pass on this branch. Python distributions and the Web production build also pass; the dependency-aware isolated wheel smoke remains evidence from the prior baseline.
- CI configuration, contributor guidance, review routing, PR template, synchronized agent rules and documentation checks are implemented.
- [Environment and operations Q&A](architecture/environment-operations-qa.md) retains design guidance for automation, clusters, traces and both execution modes; it is not runtime evidence.

## Main gaps

- Hosted CI has not run for this branch; GitHub main protection and reviewer access remain unverified. S0 acceptance is local engineering evidence, not hosted integration evidence.
- The local Run/Environment API consumes container Agent launch plans, with solver-only and isolated evaluation modes. Real model requests and real Agent tasks remain unvalidated.
- This host's Claude Code login has no copyable `.credentials.json`, so Claude container authentication needs explicit secret injection or file credentials. DSH has no generic side-effect-free authentication probe and its structured headless protocol is pinned to a preview release.
- Task authoring model orchestration, real tool injection and native benchmark evaluator equivalence remain incomplete; indexed imports are not compatibility certification. Durable leases/queues, crash recovery, distributed Worker execution and public Run gateways remain absent.
- Docker Environment applies CPU/memory and GPU UUID settings; CPU-only execution and cleanup are validated. GPU workload enforcement, Ray and multi-node authentication/deployment remain unvalidated.
- Fine-grained public/private import checks still need to accompany the remaining S1 contracts.
- Records currently provides local controller durability. Host/external Agent capture, resource time-series sampling, HTTP authorization, multi-process Worker spool, remote archival, Parquet and training-framework exporters remain unimplemented.
- Actual four-person identities/review assignments and license selection remain open.

## Next priorities

1. Complete Tasks integration: authoring orchestration, ToolBinding and native benchmark equivalence, using the task-branch foundation.
2. Connect the local Run API to CLI/HTTP and validate a real Agent task with an explicit budget.
3. Use the Records substrate for durable queue/lease recovery, then add Worker spool and Ray-backed two-node execution.

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
- [Records foundation implementation](changes/20260916-records-foundation-5c8f2d.md).
