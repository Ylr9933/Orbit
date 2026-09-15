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
    inspect_resources: Callable[[], dict[str, object]],
    validate_resource_request: Callable[[Path], dict[str, object]],
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
    doctor.add_argument("provider", help="Provider name, for example codex, claude-code, or dsh")
    setup = agent_commands.add_parser("setup", help="Install a missing provider, then check it")
    setup.add_argument("provider", help="Provider name, for example codex, claude-code, or dsh")
    resource = commands.add_parser("resource", help="Inspect and validate execution resources")
    resource_commands = resource.add_subparsers(dest="resource_command", required=True)
    resource_commands.add_parser("inspect", help="Read a host CPU, memory and GPU snapshot")
    validate = resource_commands.add_parser("validate", help="Validate a resource request YAML")
    validate.add_argument("request", type=Path)
    args = parser.parse_args(argv)
    if args.command == "config-check":
        try:
            config_result = check_config(args.config)
        except (OSError, ValueError) as error:
            parser.exit(2, f"Configuration error: {error}\n")
        print(json.dumps(config_result, sort_keys=True))
        return 0

    if args.command == "resource":
        try:
            resource_result = (
                inspect_resources()
                if args.resource_command == "inspect"
                else validate_resource_request(args.request)
            )
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(2, f"Resource error: {error}\n")
        print(json.dumps(resource_result, sort_keys=True))
        return 0

    try:
        callback = setup_agent if args.agent_command == "setup" else probe_agent
        agent_result = callback(args.provider)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"Agent diagnostic error: {error}\n")
    print(json.dumps(agent_result, sort_keys=True))
    available = agent_result.get("available") is True
    compatible = agent_result.get("compatible", True) is True
    authentication_failed = agent_result.get("authenticated") is False
    return 0 if available and compatible and not authentication_failed else 1
