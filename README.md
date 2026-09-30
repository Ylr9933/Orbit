# Orbit

Orbit lets coding agents such as Codex and Claude Code run experiments in isolated Docker containers
under GPU/CPU/memory leases, and keeps logs, metrics, code snapshots and results for review.
The agent plans and writes the code; Orbit runs and records it. A local Web UI is for review.

> Status: **R1 single-node research loop** on branch `refactor/ts-rewrite` (not yet merged).
> See [docs/status.md](docs/status.md) and the design in [docs/design.md](docs/design.md).

## Requirements

Linux, Node.js 24.18+, pnpm 10. Docker and the NVIDIA driver (CDI spec or NVIDIA Container Toolkit)
for GPU runs.

## Usage

```bash
pnpm install && pnpm build            # builds the Web UI and packages/orbit/dist
alias orbit="node $PWD/packages/orbit/dist/cli.mjs"

orbit resources                       # GPUs, CPU, memory, disk, leases and queue
orbit run --image python:3.12-slim --gpus 1 -n try -- python train.py
orbit sweep --image python:3.12-slim --gpus 1 -g lr -p lr=1e-4,3e-4 -p seed=1,2,3 \
  -- python train.py --lr {lr} --seed {seed}
orbit ps [-a] [-g lr]                 # runs; queued runs show why they wait
orbit wait -g lr                      # block until done; exit 1 if any run did not succeed
orbit logs <id> [-f] [--tail BYTES]
orbit show <id> | cancel <id> | note <id> "text"
orbit web [id]                        # open the local Web UI

orbit auth add claude --harness claude-code --kind relay --from-env   # agent credentials
orbit auth test claude                # a real run: the agent in a container must answer
orbit run --auth claude --image python:3.12-slim -- claude -p --dangerously-skip-permissions "…"
orbit notify add team --kind feishu --url-env FEISHU_HOOK --on failed,group
```

Options go before `--`; the command after it runs in `/workspace`, a snapshot of the current git
repository (including uncommitted changes). Experiments write metrics as JSON lines to
`$ORBIT_METRICS` and results to `$ORBIT_OUTPUT`. Runs that do not fit the free resources queue.

State lives in `~/.orbit` (override with `ORBIT_HOME`). The daemon starts automatically, listens on
`127.0.0.1:7717` (`ORBIT_PORT`) and writes its endpoint and token to `~/.orbit/daemon.json` (0600).

Auth profiles (`login`, `api-key`, `relay` for Codex and Claude Code) live in `~/.orbit/auth.json`
(0600). Secrets are read from stdin, an environment variable or a file, never from argv; logs are
redacted. Notifications (Feishu, DingTalk, WeCom, Slack, webhook) live in `~/.orbit/notify.json`.

## Agents

Install the skill in [plugin/](plugin/README.md) for Claude Code or Codex. Agents then estimate
resources, submit runs and sweeps, wait, read logs and record notes through `orbit`; each run links
to the agent session that submitted it.

## Development

```bash
pnpm --filter @zjunlp/orbit-web dev   # Vite dev server; proxies /api to the daemon
pnpm verify                           # lint + typecheck + boundaries + tests + build
```

## Layout

```
packages/orbit/   the `@zjunlp/orbit` package (CLI `orbit`, daemon, modules)
packages/web/     the Web UI (React, served by the daemon)
plugin/           the Orbit skill for Codex / Claude Code
scripts/          repository checks (module boundaries)
docs/             design.md, status.md, tasks/, guides/
```

Contributors and coding agents: read [AGENTS.md](AGENTS.md) first.

The previous Python implementation is kept at tag `v0-python-final`.
