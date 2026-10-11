# Service containers for Harbor docker-compose tasks
branch: feat/harbor-sidecars (on fix/harbor-verifier-modes) · status: completed · updated: 2026-10-10

## Goal
Run the 5 TB-Science tasks whose environment has a docker-compose file (tamp-skill-planning,
protein-active-learning, longitudinal-clinical-agent, noisy-blackbox-optimization,
inverse-lithography) with their service containers, isolation and limits intact, inside the same
Run, lease and cleanup rules.

## Changes
- Contract: `RunSpec.services` (`ServiceSpec`), `networks`, `runNetworks`, `dependsOn`; `Run.services`
  (container id, failure during the run); `leaseRequest` = run + services (1 CPU / 1 GB for a service without limits).
- Executor: per-run networks (internal when declared, or `default` when the run has no network),
  `--network name=,alias=`, health checks, hardening flags, optional limits; services start in
  dependency order before the run's container (failures are environment failures), are checked,
  stopped, logged and collected into `output/services/<name>/` after it, and removed with their
  networks before the lease is released. Runs with services stay on the submitting node.
- Bench: `bench/compose.ts` translates the Compose subset Harbor tasks use (interpolation with
  CONTEXT_DIR / CPUS / MEMORY / task env); other keys mark the task unsupported. Service artifacts
  come from the service; a service that broke during the solve makes the trial invalid.
- Dependency: `yaml` 2.9.1 (pinned; was already in the lockfile transitively).

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | 182 tests; one earlier run hit a flaky `snapshot.test.ts` case that passed 4× alone and in the rerun |
| Parser over TB-Science (70) | working tree | passed | 70 supported; generated specs of the 5 compose tasks parse as RunSpec |
| Real Docker: isolation probe (run + 2 services, internal networks) | working tree | passed | main reaches `svc` and the internet; `svc` on an internal network has no internet; `other` on another network is not resolvable from main; containers and networks removed |
| Real Docker: unhealthy service / service exiting mid-run | working tree | passed | `failed (service bad is unhealthy)` before start; `services[].failure = exited with code 3` recorded; cleanup done, nothing left |
| Real Docker: TB-Science longitudinal-clinical-agent (oracle, empty) | working tree | passed | oracle 1, empty 0; broker artifacts collected from `output/services/broker/` |
| Real Docker: TB-Science protein-active-learning (oracle, empty) | working tree | passed | oracle 1, empty 0 (two internal-network services, submission depends on assay) |
| Real Docker: TB-Science inverse-lithography, noisy-blackbox-optimization, tamp-skill-planning (oracle, empty) | f8466ca | passed | oracle 1, empty 0 for all three (tamp's oracle probes the `sim` service; builds took ~40 min through the slow mirror; a first attempt failed on Docker Hub timeouts) |

## Next / open issues
- Compose `service_started` on a service with a health check waits for healthy here (stricter, start-up only).
- Services without limits are leased 1 CPU / 1 GB but not capped, as in Harbor.
