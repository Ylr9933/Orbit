---
record_version: 1
task_id: "20260926-framework-maintenance-c82e61"
title: "Clarify framework boundaries and document benchmark scheduling"
branch: "refactor/0926-framework-maintenance"
base_commit: "a4941972c321f9fee6b604759b99a80cfe080c46"
work_status: completed
updated_at: "2026-09-26T13:03:55+08:00"
pull_request: null
---

## Goal and acceptance

- Audit current module responsibilities; simplify demonstrated duplication without removing supported workflows.
- Separate ASI fixture/native Docker responsibilities and Web overview/trajectory components while preserving plans, CLI, HTTP and stored evidence formats.
- Produce a detailed Chinese 0926 framework walkthrough grounded in source, covering ASI scheduling, budgets, recovery, Records and current limitations.
- Pass targeted regressions, repository checks and the standard verification suite; this maintenance task requires no new model calls.

## Changes

- Moved Docker-specific capabilities and cleanup into the Codex backend; fixture uses only the managed-process contract.
- Removed the redundant Codex interpretation wrapper by reusing the existing evidence hook on both summary-present and summary-absent paths.
- Extracted the Web trajectory panel with local pagination and Run-keyed lifecycle.
- Added the 307-line Chinese 0926 framework/scheduling walkthrough and documentation-map entry. Project overview unchanged: no new user capability or milestone is claimed.

## Decisions

- Retain distinct research and native-benchmark execution contracts: they own different protocols and are not redundant implementations.
- Keep durable admission, reconciliation and evidence collection semantics intact; do not collapse them into a single disposable runner.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git status and source audit | a494197 | passed | Clean main; inspected dispatch, queue, leases, process backend and ASI runtime. |
| ASI adapter test suite | Final task workspace | passed | 20 tests, including fixture isolation, ownership-sensitive cleanup and evidence fallback. |
| Existing prepared execution regeneration and archived real Run projection | Final task workspace against prior ASI acceptance files | passed | PreparedExecution exactly unchanged; real Records trajectory returns five steps and continuation. No model or Docker launch. |
| Adapter Ruff and Markdown checks | Final task workspace | passed | Style and links pass. |
| `make verify` | Final task workspace | passed | 399 tests, import boundaries, mypy, Ruff, Biome, TypeScript, repository links and Python/Web builds. 33 integration/E2E tests excluded; one existing Pydantic forward-reference warning. |
| New real-model/Docker/browser trial | Final task workspace | not_run | This task reorganizes internals; retains prior native acceptance evidence, uses regression tests and static Web checks. |

## Open items and blockers

- None for the maintenance scope; remaining product gaps are documented separately.

## Next steps

- None for implementation. Task branch awaits review/integration; no merge or push requested for this maintenance task.

## Compatibility and rollback

- No intended schema, command or frozen-plan change. Revert this task commit to restore prior internal organization.
