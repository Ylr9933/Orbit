# Agent Infra

A modular infrastructure project centered on **Agent** and **Environment**, coordinated through
Run, Tasks, Resources and Records, with thin protocol gateways and a Web console.

The current prototype includes replaceable Codex, Claude Code and DeepSeek Harness adapters,
Tasks and single-node Resources, a local Docker Run/Environment slice, durable Records, and
a simple local research Web console. Distributed execution and complete workflow control remain pending.
See [project status](docs/project-status.md) for acceptance and integration state.

## Quick start

Prerequisites: Linux, Git, Make, Python 3.12.14, Node 24.18.0, uv 0.12.10 and pnpm 10.32.1.
Tool installation and worktree guidance: [CONTRIBUTING.md](CONTRIBUTING.md).
Run from the repository root:

```sh
make setup
make verify
uv run --locked python scripts/ci/smoke_wheel.py
uv run --locked agent-infra --version
uv run --locked agent-infra config-check --config configs/defaults.toml
uv run --locked agent-infra agent doctor codex
uv run --locked agent-infra agent doctor claude-code
uv run --locked agent-infra agent doctor dsh
uv run --locked agent-infra resource inspect
uv run --locked agent-infra resource validate examples/resource-requests/single-gpu.yaml
pnpm build
uv run --locked agent-infra web
```

Open the token-bearing local URL printed by the Web command (port 8765). It provides host
resource monitoring, project/milestone editing, Tasks, Agent diagnostics and recorded Run traces.
See the [Web console guide](docs/operations/web-console.md) for task registration, existing Records,
SSH forwarding and current limits. Ctrl-C stops the console. `make dev-web` remains the isolated
Vite frontend development entrypoint without a default backend proxy.

`make check` runs format, lint, type, import-boundary, policy-parity and local document-link checks.
`make test` runs deterministic tests without external services. `make build` produces a Python
wheel/source distribution in `dist/` and Web assets in `src/web/dist/`. `make verify` runs all three.
Install commands require registry access (or populated caches); CI uses the same commands.

## Code organization

```text
src/agent_infra/
  agents/          Agent sessions and backend adaptation
  environments/    Workspaces, execution and environment lifecycle
  runs/            Run/Attempt orchestration
  tasks/           Task parsing, visibility and native evaluation
  resources/       Allocation, leases and dispatch
  records/         Durable metadata, events and artifact references
  contracts/       Small shared contracts, introduced in S1
  gateways/        CLI, HTTP, MCP and Worker protocol boundaries
  bootstrap/       Configuration and dependency assembly
src/web/           React/TypeScript frontend
```

The backend implements initial public contracts and local workflows across the functional modules.
See project status for validation scope and remaining integration gaps.
Cross-module calls use public contracts; concrete backends are assembled in bootstrap. The static
dependency graph is enforced by import-linter; finer public/private boundaries accompany S1
contracts.

`tests/` holds validation; `configs/` holds safe tracked configuration; `scripts/` holds developer
and CI utilities. `deploy/`, `examples/` and `schemas/` reserve deployment, examples and generated
contract locations for later stages. `.github/` holds CI and review configuration.
Runtime data belongs in ignored `var/` or an external state directory. See
[the documentation map](docs/README.md) for document placement.

## Configuration

`agent-infra config-check` validates built-in defaults, an optional explicit TOML file, then
`AGENT_INFRA_STATE_DIR` / `AGENT_INFRA_LOG_LEVEL` environment overrides. It prints the resolved
non-sensitive settings without creating state or starting services. `.env` is not auto-loaded.
See [contributor configuration guidance](CONTRIBUTING.md#configuration-and-secrets).

## Design and development

- [Agent/Environment architecture](docs/architecture/agent-environment-modules.md)
- [Agent module and replaceable CLI integrations](docs/architecture/agent-module.md)
- [Resource management, Docker and Ray design](docs/architecture/resource-management.md)
- [Environment, cluster, trace and execution-mode questions](docs/architecture/environment-operations-qa.md)
- [Development sequence](docs/development/development-sequence.md)
- [S0 plan and acceptance](docs/development/s0-engineering-foundation.md)
- [Four-person collaboration plan](docs/development/four-person-collaboration.md)
- [Agent rules](AGENTS.md), mirrored in [CLAUDE.md](CLAUDE.md)

Develop on task branches and include significant-task records. Publishing and PR merges follow
the agreed authorization and review workflow. CODEOWNERS requests review; it does not activate
branch protection. Hosted CI and main rulesets must be verified on GitHub after publishing.

License selection is pending; the empty LICENSE file grants no license.
