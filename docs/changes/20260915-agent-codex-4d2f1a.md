---
record_version: 1
task_id: "20260915-agent-codex-4d2f1a"
title: "Design replaceable command-Agent integrations"
branch: "feat/agent-codex"
base_commit: "67958a0c6feffa9b3661c53fe8bb662279fce705"
work_status: completed
updated_at: "2026-09-15T17:33:37+08:00"
pull_request: null
---

## Goal and acceptance

- Define an Agent module boundary that can support packaged CLI agents and in-process custom
  workflows without coupling Agent implementations to Docker or resource backends.
- Implement Codex CLI discovery, non-sensitive login probing, host and container launch plans,
  isolated file-based credential reuse, normalized JSONL events, and a pinned container image
  recipe.
- Expose a diagnostic CLI command and validate behavior without making a paid model request.
- Extend the same provider-selected path to Claude Code and DeepSeek Harness, sharing installation,
  probing, credential staging, launch-plan and event-normalization logic where their native CLIs
  permit it.

## Changes

- Added provider-neutral Agent discovery, request, launch-plan, mount and normalized event types,
  including compatibility reporting and a separate command-Agent protocol that does not force
  in-process workflows into a CLI.
- Added a provider registry and shared npm CLI support for discovery, installation and private
  file staging. The bootstrap layer registers Codex, Claude Code and DSH plus documented aliases.
- Added provider adapters with shell-free host/container plans and native JSONL decoding: Codex
  `exec`, Claude Code print mode, and DSH headless mode.
- Added provider-selected `agent doctor` and `agent setup` commands. DSH setup pins
  `0.1.6-alpha.1`, because the npm default `0.1.5-rc.1` lacks JSON events and session resume.
- Replaced the Codex-only Dockerfile with a common fixed-version Node Agent recipe; updated unit
  tests, README guidance, architecture navigation and the proposed S1 project-status view.

## Decisions

- This branch is based on `docs/s1-plan` as authorized by the user, so it includes the S1 planning
  commit until that parent branch is integrated or the branch is rebased.
- Agent adapters will produce runtime-neutral launch plans. Environment backends remain responsible
  for creating processes and containers.
- Container runs will receive a task-owned copy of the minimum provider files rather than a mount
  of an entire host home. User settings, MCP configuration, histories and `.env` stay excluded.
- Prompt text is supplied through stdin and launch plans contain argv arrays, so neither prompt nor
  model input is interpolated into a shell command.
- Disabling a provider's own interactive approval is accepted only for container placement where
  Environment must supply the outer isolation boundary; host plans reject that mode.
- Provider differences remain explicit: Codex resume is deferred, Claude Code accepts per-run
  model/effort/resume, and DSH reads model policy from its active profile.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `codex --version`; redacted `codex login status` exit code | Host snapshot 2026-09-15T16:35:28+08:00 | passed | Found `/home/wangxuehai/.npm-global/bin/codex`, version 0.154.0; login command returned 0 without capturing identity or credentials. |
| `make check` | Task workspace at 2026-09-15T16:57:57+08:00 | passed | Ruff, formatting, import-linter, mypy, Biome, TypeScript and documentation checks passed. |
| `make test` | Same workspace snapshot | passed | 29 deterministic tests passed, including 11 Codex adapter tests and the CLI diagnostic test. |
| `make build`; `uv run --locked python scripts/ci/smoke_wheel.py` | Same workspace snapshot | passed | Python sdist/wheel and Web production assets built; wheel installed and its CLI/package imports passed in an isolated environment. |
| `uv run --locked agent-infra agent doctor codex`; `agent setup codex` | Host snapshot 2026-09-15 | passed | Both reported Codex 0.154.0, installed, authenticated and file credentials reusable; setup did not reinstall it. |
| Docker build and credential smoke | Local Docker 29.8.0, image manifest `sha256:a1cd4f9d6e89c09d2ea7a19e4f83830a67f0c076491b996a458a489c0e141289` | passed | Built the pinned recipe; container reported Codex 0.154.0 and login status 0 using a task-private auth copy. No model request was made; temporary auth and image tag were removed. |
| `make check`; `make test` | Workspace at 2026-09-15T17:33:37+08:00 based on `9dd2d64` | passed | Ruff, formatting, import-linter, mypy, Web checks and repository checks passed; 47 deterministic tests passed across all three adapters, version calibration, registry and CLI. |
| `agent doctor codex`; `agent doctor claude`; `agent setup dsh`; provider aliases | Same host snapshot | passed | Codex 0.154.0 authenticated/reusable; Claude Code 2.1.272 authenticated but without copyable file credentials; DSH installed and calibrated from npm default 0.1.5-rc.1 to required 0.1.6-alpha.1. No identity or secret output was recorded. |
| Common Dockerfile builds and CLI smoke | Local Docker 29.8.0 | passed | Temporary images reported Codex 0.154.0, Claude Code 2.1.272, and DSH headless JSON/session options at 0.1.6-alpha.1. Image IDs were `d74c3f3e653`, `2c27c16a0af3`, and `ba4c2e7061b7`; all temporary tags were removed. No model request or real tool call ran. |
| `make verify`; `uv run --locked python scripts/ci/smoke_wheel.py` | Final workspace snapshot before commit | passed | All checks and 47 tests repeated; Python sdist/wheel, Web production assets, isolated wheel install, package import and installed CLI smoke passed. |

## Open items and blockers

- None for the approved adapter scope. Environment execution, real model runs and secret injection
  are subsequent tasks; Claude's keychain-only login and DSH's preview protocol remain documented
  compatibility limitations.

## Next steps

- Implement the Environment executor that consumes launch plans, then perform explicitly budgeted
  real host/container runs for selected providers.

## Compatibility and rollback

- The Python public surface and CLI commands are additive except for the new `compatible` probe
  field. The Codex-specific Dockerfile path is replaced by a provider-neutral path. No database or
  persistent state migration is introduced. Revert the provider extension commit to restore the
  Codex-only implementation; task-private credential copies remain runtime data.
