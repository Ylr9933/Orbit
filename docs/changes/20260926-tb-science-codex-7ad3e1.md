---
record_version: 1
task_id: "20260926-tb-science-codex-7ad3e1"
title: "Native Harbor Codex trials and TB-Science suite compatibility"
branch: "feat/tb-science-codex"
base_commit: "b7079f4c3226460639104186bddb38131dd6b216"
work_status: in_progress
updated_at: "2026-09-26T09:17:13.810495+00:00"
pull_request: null
---

## Goal and acceptance

- Enable pinned native Harbor Codex, explicit model/authentication/version, complete native evidence inventory and original scoring without changing tasks.
- Validate a real CPU Codex trial within user-approved budget; retain raw sessions, ATIF, submission and verifier results in Records.
- Inspect all pinned suite tasks offline and report per-task eligibility/resources; reuse persistent batch scheduling for admitted tasks, never silently omit unsupported tasks.

## Changes

- Native Codex request/configuration, exact version, owned host auth.json or private API-key file reference; no terminal environment inheritance assumption.
- Optional checksum-pinned native distribution reuse and solver-IP-restricted loopback proxy relay for public solver networks only; native runner/scorer and verifier network policies remain unchanged.
- Evidence inventory with file hashes, native sessions, ATIF, submission/verifier outputs, missing coverage and bounded shared Web trajectory view. Original files remain intact; collection limit 256 MiB, no silent raw truncation.
- Correct phase peak leases (solver/verifier plus sidecar), outer wall budget, safe cleanup on setup failure, credential-shaped output collection rejection.
- Offline all-task inventory, batch examples and focused regression tests.

## Decisions

- Preserve task clocks, private verifier isolation, network rules and native artifact handoff. No automatic model retry, no full-suite paid run.
- User approved gpt-6-sol / Codex 0.157.1, at most three CLI starts and 30 cumulative model minutes, local main container <=4 CPU/8 GiB plus 0.1 CPU/128 MiB native network sidecar, no GPU. Keep ASI workload untouched. No full-suite paid run.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Local source inspection | b7079f4 | passed | Native Harbor supports Codex version option and explicit auth.json path; current adapter rejects model agents. |
| 70-task offline audit at 4 CPU/8 GiB | Initial installed wheels | passed | 51 eligible; 15 over resource envelope, 4 Compose rejection. No model or Docker. |
| 70-task offline audit at 4 CPU/16 GiB | Updated installed wheels | passed | 65 eligible; four Compose rejection, one environment requirement rejection (also Compose). Inspection only, no 16 GiB runtime. |
| First native Codex trial | Installed wheels, default native installation | failed | d78a87909bb34bdeaf9851b5c4934a5d: upstream 360s Agent setup timeout while downloading apt dependencies. Zero model CLI starts; cleanup confirmed. |
| Second native trial, pinned local distribution | Updated wheels | failed | 503889b141334cbd81e57594855d43b1: CLI 0.157.1 started; direct model endpoint timed out. Explicitly cancelled and cleaned. Agent phase ~66.25s, retained partial evidence. |
| `make verify` | Code snapshot with model/profile/Web/proxy changes | passed | 410 tests, 33 deselected; lint, types, imports, documentation and Python/Web builds. Log `/tmp/tb-codex-complete-verify.log`. Subsequent adapter-only edge fixes receive focused tests. |
| Optional runtime regression tests | Current source on pinned Harbor | passed | 17 tests, including socket relay peer filtering, shutdown, IP revocation, bundle digest/version and evidence/auth boundaries. |
| Proxy-enabled real Codex acceptance | Launch-time installed wheels; snapshot in ignored trial directory | failed | Run 0909b736dfab4555ad0346e5600a548a, native trial d3ed75b1-5f58-4c29-b51e-30b2246e4407. Watchdog cancelled before verifier; no score. Agent phase 1633.06s, plus previous 66.25s = 1699.31s (<30min); two actual model CLI starts across three native trials. |
| Native evidence / Records / current parser | Launch-time outputs and c8911bc parser on a temporary copy | passed | Raw session 1,170,757 bytes, ATIF 137 steps, regressor.py and native result archived; verifier explicitly missing. Records Web projection returns 50 steps and cursor 50. Three derived steps clipped; raw session unchanged. Current parser extracts native usage. |
| Cleanup and lease reconciliation | Final persisted Run state | passed | cleanup_complete=true, lease released, no owned solver containers remain. ASI workload untouched. |
| GPU declaration review | TB source 0efab0e6d7c6af5886e838990352ab85484cc234 | passed | 70 solver declarations gpus=0; two explicit verifier declarations zero, 68 unspecified. rv-astrometry-fitting contains contradictory H100 comment; this is not proof all tasks can execute on CPU. |

## Open items and blockers

- Implementation and no-model checks passed. Real Codex solving, raw archival, partial Web view and cleanup validated; end-to-end native scoring remains unvalidated after the acceptance watchdog cancelled. No complete-suite or GPU-free execution claim.
- Launch-time wheels precede c8911bc edge hardening (IP revocation, evidence metrics/coverage, input guards); optional unit tests cover those changes and the current parser was checked on a copy of real outputs. Runtime snapshot hashes remain in ignored installed-snapshot.json.
- Main overview unchanged: this branch is not yet integrated and required full real acceptance remains incomplete.

## Next steps

- Obtain a revised acceptance budget before further model calls, or explicitly revise acceptance scope. Complete native scoring and complete evidence acceptance before reporting delivery or merging; preserve the cancelled trial unchanged.

## Compatibility and rollback

- Existing Oracle/Nop inputs keep defaults; new model profile is explicit. Restore previous adapter wheels to disable it; never rewrite or delete active runtime state.
