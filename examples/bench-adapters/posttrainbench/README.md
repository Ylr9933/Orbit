# PostTrainBench adapter

An Orbit bench adapter for [PostTrainBench](https://github.com/ai4sci-bench/PostTrainBench)
(protocol: [design §7](../../../docs/design.md#7-刷榜bench)).

PostTrainBench gives an agent a small pre-trained model (Qwen3-1.7B-Base by default),
one benchmark (GSM8K / HumanEval / GPQA / AIME / BFCL / Arena-Hard / HealthBench), a
time budget and a GPU, then measures how far the agent can post-train the model. The
adapter registers it as an Orbit benchmark, so a task × method × seed sweep is a
single `orbit bench run` with results in the Web UI.

## Requirements

- **GPU**: NVIDIA A100/H100 with 80 GB VRAM (default; override with `-c gpuMemGB=40`)
- **NVIDIA driver**: 535+. A driver without CUDA 13.0 support needs the CUDA
  forward-compatibility libraries on the host, usually at
  `/usr/local/cuda-13.0/compat/`. Override the path with `-c cudaCompat=...`, or set
  it empty to skip the mount.
- **Docker** with GPU support (`--gpus` or CDI)
- **Disk**: ~15 GB free (image ~12 GB, wheels ~2 GB)
- **Python 3 on the host**, for the `get_prompt.py` call the adapter makes

## Setup

### 1. Build the image

```bash
cd examples/bench-adapters/posttrainbench/ptb-solve

# ~2 GB of pre-compiled wheels (torch cu130 + vllm and its dependencies)
./fetch-wheels.sh

docker build -t orbit-local/ptb-solve:latest .
# Behind a different mirror:
# docker build --build-arg PIP_INDEX_URL=https://pypi.org/simple \
#              --build-arg APT_MIRROR=deb.debian.org \
#              -t orbit-local/ptb-solve:latest .
```

The image (~12 GB) ships Python 3.12, torch 2.13.0+cu130, vllm 0.31.0, flash-attn,
inspect_evals and the Codex CLI.

### 2. Get a PostTrainBench checkout

```bash
git clone https://github.com/ai4sci-bench/PostTrainBench.git /path/to/PostTrain_Agent
```

### 3. Register the benchmark

```bash
cd /path/to/Orbit

orbit bench add ptb /path/to/PostTrain_Agent \
  --adapter examples/bench-adapters/posttrainbench/adapter.py \
  --resources /path/to/PostTrain_Agent/orbit/resources.json \
  --pass-env OPENAI_API_KEY      # the writing benchmarks grade through an API

orbit bench tasks ptb            # should list the eight tasks
```

Add `-c proxy=http://172.17.0.1:7890` (see [Config](#config)) if this host reaches
the network through a proxy.

### 4. Smoke test

```bash
# empty: no training, checks the adapter chain (valid 0)
orbit bench run ptb -t gsm8k -m empty -n smoke
orbit bench show <job-id>

# oracle: must be refused, since PostTrainBench has no reference solution
orbit bench run ptb -t gsm8k -m oracle -n smoke-oracle
orbit bench show <job-id>
```

## Running experiments

### Native harness (the benchmark's own solve.sh)

Use this with your own training harness. Orbit runs the harness's `solve.sh` directly
inside the container, without a Codex or Claude Code CLI.

The decision layer reads its credentials from a dotenv file in the PostTrainBench
checkout, which the adapter mounts and sources only for `native=empty`:

```bash
cat > /path/to/PostTrain_Agent/.env << 'EOF'
export ANTHROPIC_BASE_URL=https://your-gateway.example.com
export ANTHROPIC_API_KEY=sk-...
export DECISION_MODEL=your-model-name
export DECISION_CLI_MODEL=your-model-name-flash
EOF
```

```bash
# Short smoke run first: confirms the environment, does not finish training
orbit bench run ptb -t gsm8k -m native=empty -n smoke-native --timeout 5

# The real run (10 h default budget; GSM8K takes roughly 6-8 h)
orbit bench run ptb -t gsm8k -m native=empty -n first-try --seeds 1

orbit bench show <job-id>
orbit web <job-id> --open
```

`native` is the method name the adapter looks for; the agent is `empty` because the
harness authenticates from its own dotenv file rather than an Orbit auth profile. The
same command works for the other tasks (`-t humaneval`, `-t gpqamain`, ...).

### Agent CLI (Claude Code / Codex)

Use this to measure a general-purpose coding agent. Orbit launches the CLI inside the
container with the instruction from `get_prompt.py`.

```bash
orbit auth add claude --harness claude-code --kind api-key   # or --kind relay --base-url ...
# or: orbit auth add codex --harness codex --kind api-key

orbit bench run ptb -t gsm8k -m mypt=claude-code,auth=claude -n cc-try --seeds 1
orbit bench run ptb -t gsm8k -m mypt=codex,auth=codex -n cx-try --seeds 1

# Optional model pin
orbit bench run ptb -t gsm8k -m mypt=claude-code,auth=claude,model=sonnet-4 -n cc-try
```

Agents get network access and the decontamination tools the prompt refers to, so they
may fetch extra training data and screen it themselves.

| | Native harness | Agent CLI |
|---|---|---|
| Trains the model | the harness's `solve.sh` | Codex / Claude Code |
| Credentials | dotenv file in the checkout | Orbit auth profile |
| Method spec | `-m native=empty` | `-m mypt=claude-code,auth=claude` |

## How the runs work

- **Solve**: a container from `orbit-local/ptb-solve:latest`, laid out as in
  PostTrainBench's own `run_task.sh` / `run_local.sh`: the workspace holds
  `evaluate.py`, `templates/`, `timer.sh`, and its parent holds
  `contamination_check.py` and `test_data.json` for self-decontamination. The
  PostTrainBench `src/` tree is mounted read-only; the HuggingFace cache uses the
  cache mounts described in the adapter. Only `native=empty` gets the full checkout
  and its dotenv mount with `AGENT_ENV`; Codex, Claude Code and empty methods do not.
  `final_model/` is collected when the run ends.
  - `empty`: `true`, no work (the adapter check).
  - `native`: runs the harness's `solve.sh`; the workspace becomes `/home/ben/task`,
    matching the path the script expects.
  - `codex` / `claude-code`: `agentTask`, so Orbit launches the CLI.
- **Verify**: a GPU container runs `evaluate.py --model-path <collected final_model>
  --json-output-file $ORBIT_OUTPUT/metrics.json`. Verify and score use
  `collected/home/ben/task/final_model` for `native=empty`, and
  `collected/task/final_model` for the other methods.
- **Score**: `accuracy × 100` from `metrics.json`. A run with no `final_model` (the
  `empty` method) scores a valid 0; a crashed `evaluate.py` (no metrics file) is
  invalid. `oracle` is refused: the model is the thing being trained, so no
  reference solution can be staged.

## Config

All keys are optional; pass them to `orbit bench add -c KEY=VALUE`.

| Key | Default | Meaning |
|---|---|---|
| `image` | `orbit-local/ptb-solve:latest` | solve image |
| `verifyImage` | the solve image | verify image |
| `cpus, memGB, gpus, gpuMemGB, timeoutMin` | 8, 64, 1, 80, 660 | solve resources |
| `modelToTrain` | `Qwen/Qwen3-1.7B-Base` | base model to post-train |
| `numHours` | `10` | time budget for `get_prompt.py` and `timer.sh` |
| `numGpus` | `1` | GPU count for `get_prompt.py` |
| `hfHome` | `$HF_HOME`, else `~/.cache/huggingface` | HuggingFace cache on the host |
| `cudaCompat` | `/usr/local/cuda-13.0/compat` | CUDA forward-compatibility libraries; empty skips the mount |
| `proxy` | none | HTTP(S) proxy for the container, e.g. `http://172.17.0.1:7890` for a proxy on the Docker bridge gateway |

## Adapter tests

From the Orbit repository root, using only the system Python and temporary fixtures:

```bash
python3 -B -m unittest discover -s examples/bench-adapters/posttrainbench
```

These checks also run under `pnpm verify`. They do not launch containers, train a model,
read credentials or call external services.
