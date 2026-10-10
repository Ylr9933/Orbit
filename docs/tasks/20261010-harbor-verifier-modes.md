# Harbor verifier modes and task settings
branch: fix/harbor-verifier-modes · status: completed · updated: 2026-10-10

## Goal
Parse Harbor `task.toml` the way Harbor (local checkout `09f5b964`) resolves it, and mark every
setting Orbit cannot honour as unsupported instead of silently ignoring it. First step of the
Harbor-compatibility plan (then sidecars, harness parity, shared verifier, registry datasets).

## Changes
- Verifier mode: explicit `environment_mode`, else `separate` when `[verifier.environment]` exists, else `shared`.
- Separate verifier image in Harbor's order: `[verifier.environment] docker_image` → `tests/Dockerfile`
  → `tests/docker-compose.yaml` (unsupported) → fresh copy of the task environment (resources, network,
  env inherited; `tests/` mounted at /tests).
- Solve image: `[environment] docker_image` before `environment/Dockerfile`; `[environment] workdir`.
- Network per phase: `[agent]`/`[verifier] network_mode`, else the environment's (default public,
  `allow_internet = false` → no-network). The verifier default was no-network before; TB-Science sets it explicitly.
- Harbor's `/logs/artifacts` convention directory is carried from solve to verify without a declaration.
- Unsupported (listed with a reason): allowlist networks, non-linux `os`, `gpu_types`, `tpu`, `mcp_servers`,
  `skills_dir`, `healthcheck`, `[agent]`/`[verifier] user`, `[[verifier.collect]]`, `[[steps]]`, `${VAR}` env templates,
  `docker_image` with environment files but no Dockerfile. Unknown fields stay ignored, as in Harbor.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | format, lint, types, boundaries, 177 tests, build |
| Parser over TB-Science (70) | working tree | passed | 65 supported, 5 compose — unchanged |
| Parser over harbor/examples (61) | working tree | passed | 7 supported; reasons listed per setting |
| Real Docker: fixture `fallback-env` (oracle, empty) | working tree | passed | oracle 1, empty 0: task image, env vars, workdir, no network, mounted tests |
| Real Docker: harbor/examples network matrix + separate env (4 tasks, oracle, empty) | working tree | passed | oracle 4/4 = 1, empty 0; agent no-network and verifier public checked by the tasks themselves via `/logs/artifacts` |
| Real Docker: TB-Science oracle `variable-star-vetting` | working tree | passed | reward 1 (isolated daemon, `ORBIT_HOME` apart) |
| Real Docker: 3 harbor/examples on `ubuntu:24.04` | working tree | not_run | Docker Hub unreachable from the Docker daemon |

## Next / open issues
- Agent methods always get network (the model API), even for `no-network` tasks — differs from Harbor's egress control.
- Harbor examples on `ubuntu:24.04` could not be built here: Docker Hub unreachable from the Docker daemon.
