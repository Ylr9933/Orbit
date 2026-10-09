# ASI runner compatibility and execution status
branch: fix/asi-runner-timeouts · status: completed · updated: 2026-10-09

## Goal

Make the built-in Orbit ASI adapter reject the known native false-timeout bug,
propagate genuine runner failures, and keep execution separate from scoring.
A local ASI repair does not update other users' registered ASI checkouts.

## Changes

- Inspect the selected Codex/Claude adapter and CLI as Python AST using the
  configured interpreter, without importing or changing ASI source. Refuse the
  known log-before-success timeout condition or missing failure-exit support
  before launching an Agent. Fixed/alternative implementations are accepted;
  comments and docstrings do not trigger the check. Oracle/empty bypass the
  Agent compatibility probe.
- Add `--fail-on-agent-error` to native solve commands, including baselines.
- Select native results by numeric attempt, matching score-report selection;
  show attempt status and the non-official seed31415 scope in review. Leave
  score validity and genuine failed/timeout statuses independent.
- Document the need to update Orbit and the registered ASI source separately.
  No historical results or shared daemon state are changed by this patch.

## Validation

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Existing bench tests before changes | `085f3c0` | passed | 34 tests; daemon tests use an explicitly fake ASI runner |
| New regression tests before changes | `085f3c0` + tests | failed (expected) | 13 failures reproduce missing compatibility/failure propagation/review and stale attempt selection |
| Historical and fixed real ASI source inspection | workspace | passed | The affected checkout was rejected, the locally fixed checkout accepted for both Codex/Claude, via the configured ASI Python; model/effort retained |
| `pnpm verify` | workspace | passed | 182 tests passed, 4 opt-in Docker tests skipped; format/lint, types, boundaries, CLI/Web builds passed; existing unrelated lint/build notices remain |
| Built CLI `__adapter asi solve` against real checkouts | workspace build | passed | Old checkout exits 1 with upgrade guidance; fixed checkout emits the expected solve spec; no model was launched |
| `pnpm smoke:package` | workspace build | passed | Real isolated tarball install, 8 doctor checks, CLI/exports, disposable daemon HTTP and Web assets; production daemon unchanged |
| Model/scorer execution | — | not_run | Compatibility change is verified before launch; this task does not rerun experiments or require model credentials |

## Next / open issues

- Implementation and verification complete; upstream integration is pending.
- Users must install an Orbit revision containing this change and update their
  registered ASI source; this patch does not publish a new npm release.
