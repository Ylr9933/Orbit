# Pre-flight checks and smoke runs

branch: feat/preflight-smoke · status: completed · updated: 2026-10-08

## Goal

Catch a broken run before it is queued: missing data, a full or unwritable output disk, a missing
image, no node able to take it. Let the user try a small version of the run first and submit the real
one only if that succeeds.

## Changes

- `RunService.preflight` is the one validation path: `submit` rejects on its first failure (same
  messages as before; a missing project directory is now caught here instead of at snapshot time).
- `POST /api/v1/runs/check` / `client.check`: the full list (`DoctorReport`): spec, project, image on
  this node, each mount (host path; dataset per node and whether its registered path still exists),
  output (data disk space, writable), placement (where it starts now, or why it would queue; low
  worker data disk is a warning). Creates nothing.
- `resources/disk.ts`: the disk check shared by `doctor` and the pre-flight.
- CLI `run` / `sweep`: always check first and print warnings and failures; `--check` prints all and
  submits nothing; `--smoke '<cmd>'` (+ `--smoke-timeout`, default 15 min) runs the command with the
  same settings (`sh -c`, first sweep combination's `{key}` substituted, no group, tag `smoke=true`),
  waits, and submits the real run(s) with `parentId` = the smoke run only if it succeeded.

## Validation

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Daemon test (check list, pinned/missing dataset, bad project, nothing created) | working tree | passed | `test/cluster.daemon.test.ts` (fake docker); the two daemons pin their probe, so the checks no longer depend on the runner's cores and memory |
| `pnpm verify` | working tree | passed | |
| Real CLI `--check` | this machine | passed | real Docker image lookup, real disk, 1 GPU placement; missing dataset → exit 1 |
| Real `--smoke` (fail / pass / sweep) | this machine | passed | `python:3.12-slim`; failing smoke submitted nothing; passing one linked by `parentId` |

## Next / open issues

- The smoke wait lives in the CLI: if the CLI is interrupted the real run is never submitted.
- Bench jobs have no smoke option; `-t <task>` with `--seeds 1` is the small trial for now.
- Not checked against a real worker node (placement on workers is covered by the two-daemon test).
