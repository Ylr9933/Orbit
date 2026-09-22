"""Benchmark planning and managed execution arguments; business checks are injected."""

from pathlib import Path
from typing import Any


def add_benchmark_arguments(commands: Any) -> None:
    command = commands.add_parser("benchmark", help="Plan and execute enabled benchmark adapters")
    actions = command.add_subparsers(dest="benchmark_command", required=True)
    for name in ("prepare", "run", "status", "cancel", "reconcile", "events", "artifacts"):
        entry = actions.add_parser(name)
        if name in {"prepare", "run"}:
            entry.add_argument("--config", type=Path, required=True)
        else:
            entry.set_defaults(config=None)
        if name == "prepare":
            entry.add_argument("plan", type=Path)
            entry.add_argument("--output", type=Path, required=True)
        else:
            entry.add_argument(
                "--state-dir", help="State root; benchmark state is a separate namespace"
            )
        if name == "run":
            entry.add_argument("execution", type=Path)
            entry.add_argument("--operation-id", required=True)
            entry.add_argument("--capabilities", type=Path, required=True)
            entry.add_argument("--allow-host-process", action="store_true")
        elif name not in {"prepare", "reconcile"}:
            entry.add_argument("run_id")
        if name == "events":
            entry.add_argument("--cursor")
    for name in ("adapters", "inspect", "plan", "check"):
        entry = actions.add_parser(name)
        entry.add_argument("--config", type=Path, help="Explicit trusted adapter allowlist TOML")
        if name in {"inspect", "plan"}:
            entry.add_argument("adapter", help="Enabled adapter alias")
            entry.add_argument("--source", type=Path, required=True, help="Immutable local inputs")
        if name == "plan":
            entry.add_argument("--request", type=Path, required=True, help="PlanRequest JSON")
            entry.add_argument(
                "--output", type=Path, required=True, help="New admin-only plan file"
            )
        if name == "check":
            entry.add_argument("plan", type=Path)
            entry.add_argument(
                "--capabilities", type=Path, help="Offline declarations; not runtime attestation"
            )
