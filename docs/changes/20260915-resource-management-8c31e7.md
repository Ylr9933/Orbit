---
record_version: 1
task_id: "20260915-resource-management-8c31e7"
title: "Design and implement the first resource-management slice"
branch: "feat/resource-management"
base_commit: "0851eff88ac197b0232399ea3ff6ba5b427312a1"
work_status: completed
updated_at: "2026-09-15T18:55:03+08:00"
pull_request: null
---

## Goal and acceptance

- Define how a versioned YAML request becomes an all-or-nothing CPU, memory and GPU allocation,
  including explicit temporary shortage and impossible-request outcomes.
- Implement read-only host CPU, memory and NVIDIA GPU discovery with timestamps and honest
  degradation when an optional metric source is unavailable.
- Implement a concurrency-safe single-node lease manager that keeps declared capacity, live usage
  and platform leases distinct and releases leases idempotently.
- Specify how Environment applies an allocation to Docker and how a later Ray backend performs
  multi-node admission, scheduling, authentication and communication without changing Run's
  resource contract.
- Validate deterministic behavior and inspect this host without starting containers, Ray services,
  GPU jobs or model calls.

## Changes

- Added strict version 1 resource YAML parsing with explicit byte/duration units, unknown-field
  rejection, GPU selectors, placement labels and bounded wait intent; added a tracked example.
- Added public resource request, authorized capacity, host snapshot, shortage, decision and lease
  contracts plus a `ResourceManager` protocol.
- Added Linux CPU/memory and NVIDIA GPU observation with timestamps, CPU interval sampling,
  stable GPU UUIDs, free memory/utilization/process counts and explicit degraded issues.
- Added a lock-protected local allocator with fresh-telemetry admission, all-or-nothing leases,
  idempotent retry/release, external GPU conflict checks and separate waiting/unsatisfiable results.
- Added `resource inspect` and `resource validate` CLI paths, PyYAML dependency/typing, unit tests,
  architecture guidance, README navigation and the proposed project-status update.

## Decisions

- The first implementation establishes stable local contract and monitoring behavior. Docker
  enforcement and Ray multi-node execution remain adapters that consume the same contract.
- CPU utilization is observational and does not create schedulable capacity. Memory admission uses
  both authorized remainder and live availability; GPU admission also rejects leased or externally
  occupied devices.
- Requests that cannot fit authorized capacity are rejected immediately. Temporary shortages wait
  under the Run-owned timeout; the local allocator does not hide an unbounded queue.
- Ray will be the multi-node logical scheduler, while Environment applies Docker cgroup/device
  limits and node monitoring confirms physical state. The system will not run a competing global
  scheduler beside Ray.
- Ray token authentication must be combined with a private encrypted network or secure tunnel;
  cluster automation starts from user-authorized SSH or an explicit enrollment flow.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Repository and prior task inspection | `0851eff` | passed | Started from a clean Agent task branch and created `feat/resource-management`. |
| Ray, Docker and NVIDIA official documentation review | 2026-09-15 | passed | Confirmed logical scheduling versus enforcement, Ray token authentication requirements, Docker cgroup limits and NVML monitoring scope. |
| `make check`; `make test` | Workspace at 2026-09-15T18:49:52+08:00 based on `0851eff` | passed | Dependency direction, Ruff, formatting, mypy, Web checks and repository checks passed; final suite has 66 tests, including 18 resource test cases and CLI routing. |
| `agent-infra resource validate examples/resource-requests/single-gpu.yaml` | Same workspace | passed | Parsed 2 CPU, 8 GiB memory, one GPU with 16 GiB minimum, research label and 30-minute wait timeout. |
| `agent-infra resource inspect`; logical lease/release smoke | Host `prompt`, 2026-09-15 | passed | Read 80 logical CPUs, about 251 GiB physical memory and four RTX 3090 GPUs without starting work; a request received one GPU lease and release left zero active leases. GPU UUIDs are intentionally omitted from this record. |
| Initial isolated wheel smoke with legacy `--no-deps` install | Workspace before smoke-script correction | failed | The new declared PyYAML runtime dependency was intentionally omitted by the old smoke command, so importing the CLI raised `ModuleNotFoundError: yaml`. The install procedure was corrected to resolve wheel dependencies and the full smoke was repeated. |
| `make verify`; `uv run --locked python scripts/ci/smoke_wheel.py` | Final workspace snapshot before commit | passed | All checks and 66 tests passed; Python sdist/wheel, Web assets, dependency-aware isolated wheel installation, base CLI and resource YAML validation passed. |

## Open items and blockers

- None for the approved local resource-foundation scope. Local leases and waiting are in memory;
  Run/Records must persist and recover them before a real service claims durability. Docker and Ray
  remain the documented next adapters and require their own real-environment acceptance evidence.

## Next steps

- Apply allocations in the Environment Docker adapter and verify cgroup/GPU enforcement and
  cleanup before implementing Ray.

## Compatibility and rollback

- This is additive S1/S2 groundwork. PyYAML becomes a small runtime dependency; no persistent state,
  container or Ray cluster is created. Reverting the task commit and lock change removes the new
  contract, CLI and dependency.
