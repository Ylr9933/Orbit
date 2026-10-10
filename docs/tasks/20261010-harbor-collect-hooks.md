# Harbor collect hooks and Terminal-Bench 4.0 coverage
branch: feat/harbor-collect-hooks (on feat/harbor-shared-verifier) · status: completed · updated: 2026-10-10

## Goal
Run more of Terminal-Bench 4.0 (`harbor download terminal-bench/terminal-bench@latest`, 66 tasks):
`[[verifier.collect]]` hooks, a compose `main` that repeats the prebuilt image, service `shm_size`.

## Changes
- `RunSpec.hooks` (`{ service?, command, timeoutSec }`): after the command, in the run's container
  (kept by the phase script), then — with no after phase — the run's container is stopped and the
  services' hooks run, then artifacts are collected (Harbor's order). Failures are events.
- Harbor: `[[verifier.collect]]` → hooks (`user` unsupported); compose `main.image` equal to
  `[environment] docker_image` is accepted; `shm_size` → `ServiceSpec.shmGB`.
- Mount targets under `/workspace` are allowed unless the run has a project there (TB 4.0 artifacts use it).
- Datasets on Harbor Hub are fetched with Harbor's own CLI (`harbor download <org/name@ref> -o DIR`),
  then registered with `orbit bench add NAME DIR/<name> --adapter harbor`.

## Coverage (parser, this revision)
| Dataset | Supported | Remaining reasons |
| --- | --- | --- |
| TB-Science (local checkout, 70) | 70 | — |
| Terminal-Bench 4.0 (66) | 56 | H100 `gpu_types` (3), compose `main` healthcheck / network_mode / cap_add, `skills_dir`, `[environment] healthcheck`, `mcp_servers`, `service_completed_successfully` |
| harbor/examples (61) | 27 | multi-step, allowlist networks, Windows, MCP, volumes, … |

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | 186 tests |
| Real Docker: hooks in the run's container and in a service, then collect | working tree | passed | snapshot written by the main hook and the service dump both collected |
| Real Docker: TB 4.0 `shadow-relay` (collect hook → patch artifact; oracle, empty) | working tree | passed | oracle 1, empty 0 |
| Real Docker: TB 4.0 `freight-dispatch-shift` (compose `main.image`, sidecar, `/workspace` artifact; oracle, empty) | working tree | passed | oracle 1 (after the /workspace fix; first try was rejected), empty 0 |

## Next / open issues
- GPU-type placement (`gpu_types`), `[environment] healthcheck`, compose `main` healthcheck.
