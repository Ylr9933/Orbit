"""Benchmark planning CLI arguments; all business checks are injected."""

import argparse
from pathlib import Path
from typing import Any


def add_benchmark_arguments(commands: Any) -> None:
    command = commands.add_parser("benchmark", help="Inspect and plan enabled benchmark adapters")
    actions = command.add_subparsers(dest="benchmark_command", required=True)
    for name in ("adapters", "inspect", "plan", "check"):
        entry: argparse.ArgumentParser = actions.add_parser(name)
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
