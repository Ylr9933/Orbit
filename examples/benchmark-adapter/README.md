# Independent benchmark adapter example

This is a **synthetic, planning-only** package, not an ASI, Harbor, PostTrain or PAST runner.
It uses only the public Agent Infra SDK. The four fixtures exercise external scoring,
an isolated verifier, native training/self-evaluation, and paired stateful sequences.
No model, Docker, GPU, submission or native scoring code is called.

From the Agent Infra repository, run:

```sh
uv build
uv run --locked python scripts/ci/smoke_benchmark_adapter.py
```

The check builds this independent wheel, installs both wheels in a disposable venv,
and runs the installed CLI outside the source tree. Installing alone leaves it disabled.
Only `adapters.toml` explicitly enables this distribution, entry point and SDK version.

For persistent manual exploration, install the two wheels into your own separate venv,
then use its `agent-infra` executable with absolute paths to this package:

```sh
agent-infra benchmark adapters --config /path/to/benchmark-adapter/adapters.toml
agent-infra benchmark inspect demo \
  --source /path/to/benchmark-adapter/fixtures/terminal-like \
  --config /path/to/benchmark-adapter/adapters.toml
agent-infra benchmark plan demo \
  --source /path/to/benchmark-adapter/fixtures/terminal-like \
  --request /path/to/benchmark-adapter/fixtures/terminal-like/request.json \
  --output /tmp/new-demo-plan.json \
  --config /path/to/benchmark-adapter/adapters.toml
```

`benchmark check PLAN --config CONFIG` reports missing runtime declarations (exit 1).
Adding `--capabilities /path/to/benchmark-adapter/capabilities.json` satisfies the
synthetic declarations only; `runtime_ready` remains false. Do not reuse this profile
as evidence of real backend or official benchmark compatibility.

After installation, this package's own tests use the public conformance helper:

```sh
python -m unittest discover -s /path/to/benchmark-adapter/tests
```

Copy the package to start a real adapter. Replace fixtures with a pinned native parser,
preserve native semantics, and read the repository's `docs/development/benchmark-adapters.md`
and `docs/reference/benchmark-sdk.md` for the contract and trust boundary.
