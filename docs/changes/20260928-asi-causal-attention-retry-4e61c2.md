---
record_version: 1
task_id: "20260928-asi-causal-attention-retry-4e61c2"
title: "Retry the unscored ASI-Bench b3 causal-attention instance"
branch: "feat/asi-b3-causal-attention-retry-20260928"
base_commit: "05c0836b8cb68032860c48647be591616d7d94cb"
work_status: in_progress
updated_at: "2026-09-28T11:29:36+08:00"
pull_request: null
---

## Goal and acceptance

- Run `computer_science.causal_attention__seed31415` one more time with the prior gpt-6-sol, Codex 0.157.1, b3, `medium` reasoning, 10800-second native limit, 4 CPU/8 GiB, no GPU, same proxy and Docker network settings.
- Preserve the original failed Run and its evidence; keep the retry a separate attempt with its own Run ID, original task materials, raw trace, result and cleanup evidence.
- Report whether a valid local public score was obtained; do not silently substitute a retry for the original 60-member result or claim an official score.

## Changes

- Prepared an isolated one-member local batch under `benchmark/asibench/b3-gpt-6-sol-causal-attention-retry-20260928/`. Its frozen execution digest is byte-for-byte identical to the failed member's original digest `sha256:924b940a892eeb34acca5ae34826adef12e37a132cec193f74d110ec95902c36`.
- Captured the pinned upstream task Dockerfile for image `ai4sci-bench-task:cb87a71f25e0` and started a prebuild with the same packages, Codex version, host-network proxy and task image tag. This is setup only; the new Agent Run has not been submitted.

## Decisions

- The original Run `d8d1c6b65a2142d6acdcef34da629158` failed before Codex started because the upstream ASI Docker image build timed out after 1800 seconds. Preserve that evidence and inspect the build path before spending another model attempt.
- Use a separate one-member batch directory for the retry so the original 60-member batch manifest and Web registration remain immutable.
- Prebuild the exact upstream image separately because the Dockerfile's final recursive ownership step exceeded the prior in-run build window. Building the image outside the Agent Run changes no task request, benchmark scoring rule or model setting.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Compare frozen original request and failed native result | Original batch digest `sha256:6b3a90825313a303627724bbcee15515ca86c1547f369e0f12b59e95d0c39086` | passed | `effort=medium`, model gpt-6-sol, Codex 0.157.1, b3, 10800 seconds; old Docker build timed out before Agent launch. |
| `benchmark batch prepare` and frozen-plan comparison | Retry directory at 2026-09-28 11:22 +08:00 | passed | Exactly one member; original and retry `PreparedExecution` documents are identical, including digest, resources and invocation. |
| Docker image prebuild | Retry directory at 2026-09-28 11:29 +08:00 | not_run | Still in progress at the upstream `chown -R` Dockerfile step; base, Codex and PyTorch install layers are cached. |
| Retry preparation, execution, score and cleanup | Pending | not_run | Awaiting Docker build preparation and new Run. |

## Open items and blockers

- Task Docker image is absent while its prebuild runs. The prior native build hit the 1800-second limit; the prebuild has a separate 3600-second cap. Root filesystem has about 26 GiB free and must be monitored.

## Next steps

- Prepare the same native task image, freeze one-member batch, run, supervise, and verify score and evidence.

## Compatibility and rollback

- Runtime output belongs under ignored `benchmark/asibench/`; no prior Run, benchmark source, user credentials, or unrelated containers may be altered. A retry may be cancelled by its own Run ID; no automatic further retry is authorized.
