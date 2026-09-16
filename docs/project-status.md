# Project Status

Updated at: 2026-09-16T21:09:27+08:00

Basis: integrated baseline `main@c6acc18`; this task-branch version proposes the additional
Web outcomes below after merging `feat/web-console`. Implementation completion is not merge evidence.

Current stage: S1 contracts and S2 single-node execution remain in progress; an early S4 local
console is now implemented on this branch. The project is not yet a complete production platform.

## Stage overview

| Stage | Status | Current conclusion |
| --- | --- | --- |
| S0 - repository foundation | accepted | Locked setup, dependency rules, checks, tests and Python/Web builds have local acceptance evidence. |
| S1 - contracts and task examples | in_progress | Agent, Resources, Tasks, Run/Environment and Records boundaries exist; tool binding and native benchmark equivalence remain incomplete. |
| S2 - complete single-node workflows | in_progress | Solver-only research and isolated fixture evaluation work in the CPU Docker slice; real Agent, GPU and benchmark acceptance remain. |
| S3 - two-node execution and failure handling | not_started | No verified Ray dispatch or distributed recovery. |
| S4 - frontend and batch evaluation | in_progress | Local console supports resource observation, project organization and recorded execution inspection; workflow controls and batch evaluation remain. |

## Available outcomes

- Replaceable Codex, Claude Code and DSH adapters: discovery, host/container launch plans,
  isolated configuration, provider-selected doctor/setup and JSONL normalization.
- Resources: strict YAML requests, Linux CPU/memory/NVIDIA observation and concurrency-safe
  single-node in-memory leases. Tasks: manifests, solver projections, research drafts, material
  copying/fingerprints, resource bounds and indexed benchmark imports.
- Local Run/Environment: solver-only research, frozen submissions, isolated evaluator containers,
  CPU/memory/GPU configuration and separate execution/evaluation/cleanup outcomes.
- Records: SQLite/CAS, immutable manifests, events, streams, artifacts, private evaluation tags,
  trace queries, Attempt trajectories and fixed JSONL exports.
- Web: local authenticated HTTP, real host sampling, persistent project milestones and Task/Run
  association, registered public Task views, provider diagnostics, Run/Attempt event and artifact
  summaries. See [usage and scope](operations/web-console.md); controls and downloads are absent.
- Local checks and 115 deterministic tests pass; Python/Web builds pass. Chromium verifies project
  persistence, navigation, trace/artifact views, private fixture filtering and mobile layout.
  Live startup/probes observe 80 CPU cores and four GPUs without submitting workloads.
  Prior Records acceptance includes seven real CPU Docker cases; those were not rerun for Web.

## Main gaps

- Run background control, live Agent conversation/streaming, complete log/artifact browsing,
  durable leases/queues and crash recovery; real model, GPU and native benchmark validation.
- Task authoring orchestration and ToolBinding; indexed imports are not benchmark certification.
- Host/external Agent capture, durable resource time series, Worker spool, remote archival and
  training-framework exporters. Current Web is single-administrator loopback access, not multiuser authorization.
- Ray dispatch, a verified second node and cluster administration; fine-grained public import checks.
- Claude container credentials need an explicit supported source; DSH authentication remains
  unknown under the generic read-only probe. Neither is evidence of a working container model request.
- Hosted CI, main protection/reviewer identities and license selection remain unverified/open.

## Next priorities

1. Add durable background Run start/cancel and a real Agent workflow with an explicit budget.
2. Complete Tasks tools/authoring and native benchmark equivalence with preserved evaluation boundaries.
3. Extend recovery and recording before Worker/Ray multi-node execution and live Web streams.

## Project-level blockers

Real Agent validation needs a configured image, credentials and model budget. Multi-node
validation needs an authorized second node and private network. Hosting and publishing remain
with the maintainer.

## Related records

- [S0 acceptance](changes/20260915-s0-foundation-b7e492.md) and [development sequence](development/development-sequence.md).
- [Run/Environment](changes/20260915-run-environment-91c2ae.md) and [Records foundation](changes/20260916-records-foundation-5c8f2d.md).
- [Web design](changes/20260916-web-console-design-94b2ad.md) and [Web implementation](changes/20260916-web-console-3c7e91.md).
