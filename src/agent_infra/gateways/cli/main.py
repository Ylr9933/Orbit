"""CLI parsing only; configuration behavior is injected by bootstrap."""

import argparse
import json
from collections.abc import Callable, Sequence
from importlib.metadata import version
from pathlib import Path


def run(
    check_config: Callable[[Path | None], dict[str, str]],
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Agent Infra engineering utilities")
    parser.add_argument("--version", action="version", version=version("agent-infra"))
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser(
        "config-check", help="Validate configuration; creates no runtime state"
    )
    config.add_argument("--config", type=Path, help="Optional TOML file")
    args = parser.parse_args(argv)
    try:
        result = check_config(args.config)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Configuration error: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0
