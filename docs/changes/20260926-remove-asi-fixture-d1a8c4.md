---
record_version: 1
task_id: "20260926-remove-asi-fixture-d1a8c4"
title: "Remove the ASI fixture execution profile"
branch: "refactor/remove-asi-fixture"
base_commit: "b2534e6b8852094dd3d0d5b35ec2e5e907122777"
work_status: completed
updated_at: "2026-09-26T05:33:37.125587+00:00"
pull_request: null
---

## Goal and acceptance

- Remove the ASI fixture entry point, simulated agent, sample configuration and runtime branch.
- Preserve real Codex plan, evidence and cleanup behavior; reject legacy fixture requests without launching a model.
- Validate adapter tests, package discovery, existing prepared execution compatibility and repository checks without new Docker/model calls.

## Changes

- Removed fixture package entry, allowlist entry, request/capability samples, simulated Agent and runtime mode.
- Collapsed Codex profile into one Adapter and removed the fixture-only backend inheritance layer. Real profile identity, resources, native invocation, evidence and cleanup remain unchanged.
- Updated ASI README, operations and implementation guides, the 0926 walkthrough and proposed project overview. Historical task records and persisted Records are untouched.

## Decisions

- Keep `asi-bench-codex-os` unchanged. Never remap a no-model fixture plan to paid execution.
- Build on the unmerged framework maintenance branch; integration is not requested.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Initial Git and source inspection | b2534e6 | passed | Clean worktree; fixture has separate entry, runner branch and sample files. |
| Adapter pytest against source and rebuilt wheel | Final task code snapshot based on b2534e6 | passed | 21 tests in each run; legacy requests rejected, native plan/evidence/provenance/cleanup regressions covered. |
| Wheel build, isolated installation, metadata discovery and old-entry rejection | Final task code snapshot | passed | Only asi-bench-codex-os is installed; loading the removed asi-bench entry raises AdapterError. |
| prepare_execution against prior real-prepared.json | Rebuilt wheel with existing real acceptance plan | passed | PreparedExecution equality exact; no execution started. |
| make verify | Final task code snapshot | passed | 399 tests, 33 integration/E2E deselected; existing Pydantic warning. Lint, types, import boundaries, policy/links and Python/Web builds pass. Log: /tmp/agent-infra-remove-asi-fixture-verify.log. |
| Adapter Ruff and final Markdown links/diff checks | Final task workspace | passed | No dependency changes; lockfiles unchanged. |
| Real Docker/model trial | Final task workspace | not_run | Removal uses regressions and prior-plan equality; no new runtime capability claimed. |

## Open items and blockers

- None for this removal scope.

## Next steps

- Implementation complete on task branch, not merged or pushed. Upgrade installed adapters to refresh entry-point metadata before use.

## Compatibility and rollback

- Legacy fixture plans no longer execute. Records remain untouched. Real Codex profile ID and serialized request fields remain stable. Revert this task to restore fixture support.
