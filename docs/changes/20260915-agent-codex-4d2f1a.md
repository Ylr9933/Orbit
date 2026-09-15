---
record_version: 1
task_id: "20260915-agent-codex-4d2f1a"
title: "Design the Agent module and implement the Codex CLI adapter"
branch: "feat/agent-codex"
base_commit: "67958a0c6feffa9b3661c53fe8bb662279fce705"
work_status: completed
updated_at: "2026-09-15T16:57:57+08:00"
pull_request: null
---

## Goal and acceptance

- Define an Agent module boundary that can support packaged CLI agents and in-process custom
  workflows without coupling Agent implementations to Docker or resource backends.
- Implement Codex CLI discovery, non-sensitive login probing, host and container launch plans,
  isolated file-based credential reuse, normalized JSONL events, and a pinned container image
  recipe.
- Expose a diagnostic CLI command and validate behavior without making a paid model request.

## Changes

- Added provider-neutral Agent discovery, request, launch-plan, mount and normalized event types,
  with a separate command-Agent protocol that does not force in-process workflows into a CLI.
- Added the Codex adapter: host discovery/version/login checks, idempotent installation, isolated
  file credential staging, safe host/container argv generation and JSONL event decoding.
- Added `agent-infra agent doctor codex` and `agent-infra agent setup codex` through the thin CLI
  gateway and bootstrap composition root.
- Added a pinned Codex 0.154.0 container recipe, unit tests, user-facing README guidance, the Agent
  architecture document, documentation navigation and the proposed S1 project-status update.

## Decisions

- This branch is based on `docs/s1-plan` as authorized by the user, so it includes the S1 planning
  commit until that parent branch is integrated or the branch is rebased.
- Agent adapters will produce runtime-neutral launch plans. Environment backends remain responsible
  for creating processes and containers.
- Container runs will receive a task-owned copy of the file credential rather than a mount of the
  entire host Codex home.
- Prompt text is supplied through stdin and launch plans contain argv arrays, so neither prompt nor
  model input is interpolated into a shell command.
- Bypassing Codex's own sandbox is accepted only for container placement where Environment must
  supply the outer isolation boundary; host plans reject it.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `codex --version`; redacted `codex login status` exit code | Host snapshot 2026-09-15T16:35:28+08:00 | passed | Found `/home/wangxuehai/.npm-global/bin/codex`, version 0.154.0; login command returned 0 without capturing identity or credentials. |
| `make check` | Task workspace at 2026-09-15T16:57:57+08:00 | passed | Ruff, formatting, import-linter, mypy, Biome, TypeScript and documentation checks passed. |
| `make test` | Same workspace snapshot | passed | 29 deterministic tests passed, including 11 Codex adapter tests and the CLI diagnostic test. |
| `make build`; `uv run --locked python scripts/ci/smoke_wheel.py` | Same workspace snapshot | passed | Python sdist/wheel and Web production assets built; wheel installed and its CLI/package imports passed in an isolated environment. |
| `uv run --locked agent-infra agent doctor codex`; `agent setup codex` | Host snapshot 2026-09-15 | passed | Both reported Codex 0.154.0, installed, authenticated and file credentials reusable; setup did not reinstall it. |
| Docker build and credential smoke | Local Docker 29.8.0, image manifest `sha256:a1cd4f9d6e89c09d2ea7a19e4f83830a67f0c076491b996a458a489c0e141289` | passed | Built the pinned recipe; container reported Codex 0.154.0 and login status 0 using a task-private auth copy. No model request was made; temporary auth and image tag were removed. |

## Open items and blockers

- None for this scoped Agent adapter. End-to-end task execution remains a separate Environment,
  Run and Records integration task.

## Next steps

- Review the public boundary and integrate this branch after deciding whether its parent
  `docs/s1-plan` commit will merge first or travel in the same PR.

## Compatibility and rollback

- The Python public surface and CLI commands are additive. No database, configuration or persistent
  state migration is introduced. Revert the task commit to remove the adapter and image recipe;
  task-private credential copies are runtime data and were removed after validation.
