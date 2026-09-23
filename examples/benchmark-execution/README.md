# Managed process execution example

Independent SDK 1.0 adapter with execution extension 1.0. It runs a trusted, short
Python sum fixture and writes `result.json`. It is not an official benchmark or Agent.
No model, network, GPU, Docker, private grader, or numeric resource allocation is used.

The package imports only public Benchmark and Environment contracts. Install its wheel
alongside the core wheel in a dedicated environment; enable it with `adapters.toml`.
`capabilities.json` covers only these exact synthetic fixture and runner digests.

From the core repository, a disposable installed-package test is available:

```sh
uv build
uv run --locked python scripts/acceptance/benchmark_execution.py
```

The script builds this wheel, installs both wheels outside the checkout, and tests
plan/check/prepare/run, two-operation FIFO admission, persistent leases, fresh CLI processes,
duplicate operation IDs, Records bytes and artifacts, and explicit host-execution opt-in. It
cleans only its temporary operations and state.

For manual commands, limitations and recovery behavior, see
[BM01 reference](../../docs/reference/benchmark-execution.md).
