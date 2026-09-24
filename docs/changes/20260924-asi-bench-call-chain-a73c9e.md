---
record_version: 1
task_id: "20260924-asi-bench-call-chain-a73c9e"
title: "Explain the implemented ASI-Bench adapter and execution path"
branch: "docs/asi-bench-call-chain"
base_commit: "00d8b0908036928280ff39a7c288c3371944b33d"
work_status: completed
updated_at: "2026-09-24T15:14:37+08:00"
pull_request: null
---

## Goal and acceptance

- Explain in Chinese the current ASI-Bench adaptation, end-to-end invocation path, evidence flow and practical limits, grounded in the actual repository code.
- Keep the existing implementation guide authoritative and link the operational guide rather than duplicate its full commands.

## Changes

- Expanded `docs/implementation/benchmark-asi-bench.md` with a call-chain diagram, each planning/execution/collection stage, recovery behavior and fixture-versus-real-run boundary.

## Decisions

- Documentation-only task; no product capability or project-status change.
- Describe the current fixed fixture implementation rather than imply that a Codex agent can be selected by changing a parameter.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Source audit of adapter, CLI, planning, run service and process backend | `00d8b0908036928280ff39a7c288c3371944b33d` | passed | Cross-checked each documented stage against source; no real benchmark invoked. |
| `.venv/bin/python scripts/ci/check_repository.py` | Task branch workspace after documentation edit | passed | Policy mirrors and local Markdown links passed. |
| `git diff --check` and final diff review | Task branch workspace after documentation edit | passed | No whitespace errors, unrelated files or secrets; documentation only. |

## Open items and blockers

- None for the documentation task. Real ASI-Bench execution was not part of this change.

## Next steps

- None for the authorized work; merge the reviewed task branch separately if desired.

## Compatibility and rollback

- No runtime interface, configuration or deployment change. Revert the documentation commit if its explanation becomes stale.
