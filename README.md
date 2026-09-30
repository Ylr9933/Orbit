# Orbit

Orbit lets coding agents such as Codex and Claude Code run experiments in isolated Docker containers
under GPU/CPU/memory leases, and keeps logs, metrics, code snapshots and results for review.
The agent plans and writes the code; Orbit runs and records it. A local Web UI is for review.

> Status: **R0 skeleton**. Only `orbit resources` and `orbit doctor` work so far.
> See [docs/status.md](docs/status.md) and the design in [docs/design.md](docs/design.md).

## Requirements

Linux, Node.js 24.18+, pnpm 10. Docker and the NVIDIA driver for GPU runs.

## Development

```bash
pnpm install
pnpm orbit resources      # GPUs, CPU, memory, disk (starts the local daemon if needed)
pnpm orbit doctor         # checks node, git, docker, nvidia-smi
pnpm verify               # lint + typecheck + boundaries + tests + build
```

State lives in `~/.orbit` (override with `ORBIT_HOME`). The daemon listens on `127.0.0.1:7717`
and writes its endpoint and token to `~/.orbit/daemon.json` (mode 0600).

## Layout

```
packages/orbit/   the `@zjunlp/orbit` package (CLI `orbit`, daemon, modules)
scripts/          repository checks (module boundaries)
docs/             design.md, status.md, tasks/, guides/
```

Contributors and coding agents: read [AGENTS.md](AGENTS.md) first.

The previous Python implementation is kept at tag `v0-python-final`.
