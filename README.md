# Orbit

[中文](README.zh-CN.md)

Orbit lets coding agents such as Codex and Claude Code run experiments safely on your GPU machines.
The agent plans and writes the code; Orbit runs it in an isolated Docker container under a GPU / CPU /
memory lease and keeps everything needed to review it afterwards: the exact code (commit + uncommitted
diff), logs, metrics, outputs and the agent session that submitted it. You review through the CLI or a
local Web UI.

> Status: version 0.1.0, under active development. Single-machine use (R0–R2) is validated; benchmarks
> (R3) and multi-node placement (R4) are implemented and still being tested.
> See [docs/status.md](docs/status.md) and the design in [docs/design.md](docs/design.md).

For a visual introduction, see the [HTML presentation (Chinese)](docs/ppt/README.md).
Open `docs/ppt/index.html` in a browser to present offline.

## Features

- **Isolated runs**: every run is a Docker container (or a host process for native benchmark
  runners) with its own code snapshot in `/workspace`; your repository is never modified.
- **Resource leases and a queue**: GPUs, CPUs and memory are leased per run; runs that do not fit
  wait in a queue that says why. GPUs, CPUs and memory used by processes outside Orbit are taken
  into account (busy GPUs are not leased; new runs wait while other processes keep the CPUs busy).
- **Sweeps and groups**: one command submits a parameter grid; `wait`, `ps` and the Web UI work on
  whole groups.
- **Records for review**: commit and diff, logs, JSON-lines metrics with charts, output files,
  events, notes, and a link to the Codex / Claude Code session that started the run.
- **Web UI**: run list, run details (overview, logs, metrics, artifacts, diff, session), run
  comparison, resources, settings and benchmark pages, served by the local daemon.
- **Agent credentials**: Codex and Claude Code can run *inside* containers with login, API-key or
  relay profiles; secrets never go on the command line and are redacted from logs.
- **Notifications**: Feishu, DingTalk, WeCom, Slack or a generic webhook when runs or groups finish.
- **On your phone**: `orbit feishu init` sets up a Feishu bot from one QR scan; it sends result cards with
  metric curves and answers `/gpu` and `/runs`.
- **Benchmarks**: task × method × seed jobs; each trial is a solve run plus a separate verify run, and
  only valid scores enter means. Adapters for Harbor task directories (e.g. Terminal-Bench Science)
  and ASI-Bench.
- **Several machines**: one machine places runs on worker machines; code travels by content hash,
  datasets are registered by name on each node, logs and metrics flow back. No Ray needed.
- **Agent skill**: a skill for Claude Code and Codex that teaches them to estimate resources, submit,
  wait and record conclusions through `orbit`.

## Requirements

- Linux.
- Node.js 24.18 or later (24.x). pnpm 10 is only needed for source development.
- Docker, usable by your user without `sudo` (e.g. a member of the `docker` group).
- For GPU runs: the NVIDIA driver and either an NVIDIA CDI spec or the NVIDIA Container Toolkit.
- git (for code snapshots).
- Optional: the `codex` and/or `claude` CLIs on the host, if agents should run inside containers.

## Installation

The npm distribution is prepared; the first public release is pending. Once published, try Orbit
without a source checkout:

```bash
npx -y @zjunlp/orbit doctor
```

Or install the CLI permanently in one command:

```bash
npm install -g @zjunlp/orbit
```

The examples below use `orbit`; without a global install, replace it with `npx -y @zjunlp/orbit`.
The package includes the CLI, daemon and built Web UI. No pnpm, manual build or symlink is needed.
To update: `npm install -g @zjunlp/orbit@latest && orbit daemon --stop` (the next command starts the
new daemon; running containers keep going and are reattached).

For installation from a checkout, see [Development](#development).

## First use

```bash
orbit doctor                    # checks docker, nvidia-smi, git, node and the Agent CLIs
orbit resources                 # GPUs, CPU, memory, disk, leases and the queue
```

The first `orbit` command starts a background daemon automatically. It listens only on
`127.0.0.1:7717` and keeps its state in `~/.orbit`. Every user runs their own daemon: when another
user's daemon already holds 7717, yours takes a free port (the CLI finds it through `~/.orbit`).

Run something from inside a git repository:

```bash
cd ~/my-project
orbit run --image python:3.12-slim -n hello -- python -c 'print("hello from orbit")'
orbit ps -a                     # the run and its state
orbit logs <id>                 # its output
orbit web                       # prints a login URL for the Web UI (add --open to open a browser)
```

Options go before `--`; everything after `--` is the command. It runs in `/workspace`, a copy of the
current git repository including uncommitted and untracked (not ignored) files.

To let an agent use Orbit, install the skill (see [Agent integration](#agent-integration)) and ask it
to run your experiment with Orbit.

## Usage

### Inside a run

| Path / variable | Meaning |
| --- | --- |
| `/workspace` | Writable copy of your code (the original repository is untouched) |
| `$ORBIT_OUTPUT` (`/orbit/output`) | Put results here; they are kept and shown in the Web UI |
| `$ORBIT_METRICS` (`/orbit/metrics.jsonl`) | One JSON object per line, e.g. `{"step": 10, "loss": 0.3}`; charted in the Web UI |
| `$ORBIT_RUN_ID` | The run id |

Leased GPUs are the only GPUs visible in the container. Runs use your host `uid:gid` by default so
output files belong to you (`--root` to run as root).

### Runs

```bash
orbit run --image pytorch/pytorch:latest --gpus 1 --mem 32 -n baseline -- python train.py
orbit run --dockerfile docker/Dockerfile --gpus 2 --gpu-mem 40 -- python train.py   # build an image
orbit run --gpus 1 --timeout 120 -w --image ... -- python eval.py   # wait; exit code = run result
```

Common options:

| Option | Meaning |
| --- | --- |
| `--image` / `--dockerfile` | Image to use, or a Dockerfile to build (context: its directory) |
| `--gpus`, `--gpu-mem <GB>`, `--gpu-ids` | Number of GPUs, minimum memory per GPU, pin specific GPUs |
| `--cpus` (default 4), `--mem <GB>` (default 16) | CPU and memory limits |
| `-n`, `-g`, `-t KEY=VALUE` | Name, group and tags |
| `-m src:dst[:rw]`, `-d name[:dst[:rw]]` | Bind-mount a host path or a registered dataset (read-only by default) |
| `-e KEY=VALUE` | Environment variable (stored with the run: no secrets) |
| `--pass-env VAR` | Pass a variable from the daemon's environment (for secrets; not stored) |
| `--project <dir>`, `--no-project`, `--no-snapshot` | Choose the repository, run without one, or mount it read-only instead of copying it |
| `--no-network`, `--host-network` | Disable networking, or share the host network |
| `--timeout <min>` | Stop the run after this long |
| `--node <name>` | Run on a specific node (multi-node) |
| `-w`, `--json` | Wait for the result; print JSON |

### Sweeps

```bash
orbit sweep --image python:3.12-slim --gpus 1 -g lr -p lr=1e-4,3e-4 -p seed=1,2,3 \
  -- python train.py --lr {lr} --seed {seed}
orbit wait -g lr                # block until the group is done; exit 1 if any run failed
```

`{key}` in the command is replaced by each value; 2 × 3 = 6 runs are submitted and queued as
resources allow.

### Following and reviewing runs

```bash
orbit ps                        # active runs; queued runs show why they wait
orbit ps -a -g lr               # all runs of a group
orbit show <id>                 # details and latest metrics
orbit logs <id> -f              # follow the log (--tail BYTES to start near the end)
orbit wait <id>...              # wait for specific runs
orbit cancel <id>...
orbit rm <id>... | -g <group>   # permanently delete finished runs (asks you to type the id or group)
orbit note <id> "lr 3e-4 diverges after step 2k"   # attach a conclusion (- reads stdin)
orbit web <id> --open           # open the run in the Web UI
```

Most commands accept `--json` for scripts and agents.

### Web UI

`orbit web` prints a URL that logs your browser in with the daemon's token (stored as a cookie).
Pages: runs (filter, group, multi-select), run detail (overview, logs with search, metric charts,
artifacts preview, code diff, agent session), compare (metrics of several runs), resources (GPUs,
leases, queue, worker nodes), bench jobs and comparisons, and settings (doctor, auth and notification
profiles). Keyboard shortcuts are listed with `?`.

The daemon listens on `127.0.0.1` only. To view it from another machine, use an SSH tunnel:
`ssh -L 7717:127.0.0.1:7717 gpu-server`, then open the printed URL locally (use the port in the URL that
`orbit web` prints if your daemon is not on 7717).

### Agent integration

With Claude Code installed, install both Orbit skills in one command (after the npm release):

```bash
npx -y @zjunlp/orbit plugin install
```

This registers the `zjunlp/Orbit` GitHub marketplace and installs `orbit@orbit` for your user.
Restart Claude Code to load `/orbit:orbit` and `/orbit:orbit-bench`. The skills use `npx` when
`orbit` is not on PATH. A local checkout can be tested with `pnpm orbit plugin install --source .`.
Manual marketplace installation and Codex skill installation are in [plugin/README.md](plugin/README.md).

The CLI needs network access to reach the local daemon. Each run records the agent session that
submitted it, and the Web UI shows that transcript. MCP is not implemented yet; this plugin uses
the existing CLI and HTTP API.

### Agents inside runs (auth profiles)

A run can execute Codex or Claude Code inside its container (for agent experiments and benchmarks).
Orbit mounts the CLI installed on the host and injects credentials from a profile:

```bash
orbit auth add codex --harness codex --kind login     # `codex login --device-auth` in a private home
orbit auth add gpt --harness codex --kind api-key --key-env OPENAI_API_KEY
orbit auth add claude --harness claude-code --kind login --key-stdin    # paste a `claude setup-token` token
orbit auth add relay --harness claude-code --kind relay --base-url https://relay.example --key-env RELAY_KEY
orbit auth add claude --harness claude-code --kind relay --from-env    # take key, URL, models from env / Claude settings
orbit auth list
orbit auth test claude          # a real small run: the agent must answer
orbit run --auth claude --image python:3.12-slim -- claude -p --dangerously-skip-permissions "…"
```

Secrets are read from stdin, an environment variable or a file, never from arguments. Profiles are
stored in `~/.orbit/auth.json` (mode 0600) and secret values are redacted from run logs. Use
`--host-network` on a profile when the agent must reach a proxy on `127.0.0.1`.

### Notifications

```bash
orbit notify add team --kind feishu --url-env FEISHU_HOOK --on failed,group
orbit notify test team
orbit notify list
```

Kinds: `feishu`, `dingtalk`, `wecom`, `slack`, `webhook`. Events: `succeeded`, `failed`, `group` (one
summary when a group has finished). Failure messages include the reason and the last log lines.

### On your phone (Feishu bot)

```bash
orbit feishu init phone       # prints a QR code: scan it with the Feishu app and confirm
```

Scanning creates a Feishu app (bot, message permissions and the message event pre-filled) paired with
whoever scanned it. Then:

- When a run or group finishes, the bot sends a card: state, resources and measured peaks, metric curves
  (e.g. loss), and the log tail for failures.
- Message the bot at any time (mention it in groups): `/gpu` shows memory, utilization and holder of each
  GPU plus CPU, memory and the queue; `/runs` the recent runs; `/show <run id>` one run. Commands are
  read-only.

The daemon opens an outbound long connection to Feishu: no public address is needed and the daemon still
listens on localhost only. If `init` reports that the long connection or the test card failed, it prints
the console page to fix (subscription mode "persistent connection", permissions, publish a version);
then run `orbit feishu check phone` to reconnect and test.

- Several bots can be bound (with different names), but each app only once, and never to the daemons of
  two machines (Feishu hands each event to only one connection). Pairing with several bots duplicates
  notifications.
- An existing app: `orbit notify add phone --kind feishu-app --app-id cli_… --secret-stdin`. Others who
  message the bot get a pairing code and can use it after you run `orbit notify pair phone <code>`;
  unpaired people see no data.
- `orbit notify list` shows paired users and the connection; `orbit notify rm phone` removes the bot.

### Benchmarks

```bash
orbit bench add tbs ../terminal-bench-science --adapter harbor
orbit bench add asi ../ASI-Bench --adapter asi -c python=/path/to/venv/bin/python --pass-env JUDGE_KEY
orbit bench add rcb ../ResearchClawBench --adapter ./examples/bench-adapters/researchclawbench/adapter.py \
  --pass-env OPENAI_API_KEY --pass-env OPENAI_BASE_URL
orbit bench tasks tbs           # tasks, and why unsupported ones cannot run
orbit bench run tbs -t symbolic-regression -m oracle -m empty \
  -m gpt=codex,auth=gpt,model=gpt-5,effort=high --seeds 3 -n first-try
orbit bench jobs
orbit bench show <job>
orbit bench compare <job>...    # per-task comparison; paired means use tasks valid for every method
orbit bench usage <job>...      # measured peak memory / CPU / GPU per task, suggested resources
orbit bench cancel <job>
orbit bench rm-job <job>        # delete a finished job with its trials and runs (type the job id)
```

Methods are `name=agent[,auth=P,model=M,effort=E,bundle=DIR]` with agent `codex`, `claude-code`,
`oracle` (reference solution) or `empty` (submits nothing; checks that the verifier gives 0). Every
trial records execution (how the solve run ended), evaluation (`valid` / `invalid` / `unknown`) and
cleanup separately; only valid scores count. The Web UI shows jobs, a task × method matrix and
cross-job comparison under **Bench**. Grader secrets given with `--pass-env` reach only the verify
run. Per-task solve resources (GPU, memory, CPU, timeout) come from an optional JSON file given with
`orbit bench add --resources`; every run records its measured peaks, and a solve run killed for memory
makes the trial invalid instead of a zero. Any other benchmark needs only an adapter executable that speaks a small JSON protocol (no
rebuild of Orbit): [docs/guides/bench-adapter.md](docs/guides/bench-adapter.md).

### Several machines

Every machine runs Orbit. The machine your agent works on (the primary) places runs on workers it has
added; local resources are used first.

```bash
# on the worker (e.g. Tailscale address 100.64.0.12); its firewall must let the primary reach 7718
orbit node expose --listen 100.64.0.12:7718
orbit node token                                # copy the printed token
# on the primary: asks for the token (paste it, input hidden, then Enter)
orbit node add http://100.64.0.12:7718
orbit node ls
orbit data add imagenet /data/imagenet          # on every node that has the data
orbit run -d imagenet --gpus 1 --image pytorch/pytorch -- python train.py
```

Code snapshots are sent once per content hash; datasets are never copied; logs and metrics are
mirrored to the primary; outputs stay on the worker and are read through the primary. The cluster
protocol is plain HTTP with a token: use Tailscale, a private network or an SSH tunnel, never the
public internet. Details: [docs/guides/multi-node.md](docs/guides/multi-node.md).

## Configuration and files

| Item | Default | Override |
| --- | --- | --- |
| State directory (database, profiles, config) | `~/.orbit` | `ORBIT_HOME` |
| Data directory (run directories, bench staging, code bundles) | the state directory | `orbit config data <dir>`, or `ORBIT_DATA` |
| Daemon port (on `127.0.0.1`) | 7717, else a free port | `ORBIT_PORT`, or `orbit daemon --port` (then a busy port is an error) |
| Node name | host name | `ORBIT_NODE` |
| GPUs Orbit may use | all | `ORBIT_GPUS=0,1` |
| Daemon endpoint and token | `~/.orbit/daemon.json` (0600) | |

The daemon is the only writer of Orbit's state; the CLI, the Web UI and agents all go through its
local HTTP API. `orbit daemon --stop` stops it; running containers continue and are picked up again
when it restarts. `orbit daemon` runs it in the foreground.

Run data can grow to hundreds of GB. On a machine with a small system disk, put it on a large disk
once, before the first runs: `orbit config data /data/$USER/orbit && orbit daemon --stop`.
`orbit doctor` warns when the data directory or Docker's data root is on the system disk or low on
space. Folders organize runs and bench jobs without moving files: `orbit run --folder rcb/noskills`,
`orbit mv <id...> rcb/archive`, `orbit folders`, and `orbit export rcb /path/to/copy` for a real copy.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `orbit doctor` reports docker errors | Docker is running and your user can run `docker ps` without sudo |
| GPU runs fail to start | `nvidia-smi` works; the NVIDIA Container Toolkit or a CDI spec is installed |
| A run stays `queued` | `orbit ps` shows the reason (GPUs busy, CPUs busy outside Orbit, memory, pinned node offline, …) |
| An agent cannot reach Orbit | `orbit` is on its `PATH`; Codex sandbox allows network access |
| Snapshot too large | Add data and weights to `.gitignore` and mount them with `-m` or `orbit data` |

## Development

Requires pnpm 10 (`corepack enable`). See the [release guide](docs/guides/releasing.md) for publishing.

```bash
git clone https://github.com/zjunlp/Orbit.git
cd Orbit
pnpm install
pnpm build
pnpm orbit doctor
pnpm --filter @zjunlp/orbit-web dev   # Vite dev server; proxies /api to the daemon
pnpm orbit <args>                     # run the CLI from source
pnpm verify                           # lint + typecheck + module boundaries + tests + build
```

```
packages/orbit/   the `@zjunlp/orbit` package (CLI `orbit`, daemon, modules)
packages/web/     the Web UI (React + Vite, served by the daemon)
plugin/           the Orbit skill for Codex / Claude Code
scripts/          repository checks (module boundaries)
docs/             design.md, status.md, tasks/, guides/, ppt/
```

Contributors and coding agents: read [AGENTS.md](AGENTS.md) first.

## License

[MIT](LICENSE) © 2026 ZJUNLP
