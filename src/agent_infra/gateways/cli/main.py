"""CLI parsing only; configuration behavior is injected by bootstrap."""

import argparse
import json
from collections.abc import Callable, Sequence
from importlib.metadata import version
from pathlib import Path


def run(
    check_config: Callable[[Path | None], dict[str, str]],
    probe_agent: Callable[[str], dict[str, object]],
    setup_agent: Callable[[str], dict[str, object]],
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Agent Infra engineering utilities")
    parser.add_argument("--version", action="version", version=version("agent-infra"))
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser(
        "config-check", help="Validate configuration; creates no runtime state"
    )
    config.add_argument("--config", type=Path, help="Optional TOML file")
    agent = commands.add_parser("agent", help="Inspect configured Agent providers")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    doctor = agent_commands.add_parser("doctor", help="Check provider installation and login")
    doctor.add_argument("provider", choices=("codex",))
    setup = agent_commands.add_parser("setup", help="Install a missing provider, then check it")
    setup.add_argument("provider", choices=("codex",))
    args = parser.parse_args(argv)
    if args.command == "config-check":
        try:
            config_result = check_config(args.config)
        except (OSError, ValueError) as error:
            parser.exit(2, f"Configuration error: {error}\n")
        print(json.dumps(config_result, sort_keys=True))
        return 0

    try:
        callback = setup_agent if args.agent_command == "setup" else probe_agent
        agent_result = callback(args.provider)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"Agent diagnostic error: {error}\n")
    print(json.dumps(agent_result, sort_keys=True))
    return 0 if agent_result.get("available") and agent_result.get("authenticated") else 1
