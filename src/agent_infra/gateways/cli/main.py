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
    *,
    task_action: Callable[[str, dict[str, str]], dict[str, object]] | None = None,
    records_action: Callable[[str, dict[str, str]], dict[str, object]] | None = None,
    web_action: Callable[[Path, Path, Path, tuple[Path, ...], int], int] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Agent Infra engineering utilities")
    parser.add_argument("--version", action="version", version=version("agent-infra"))
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web", help="Start the local research console")
    web.add_argument("--records-root", type=Path, default=Path("var/runs/_records"))
    web.add_argument("--console-dir", type=Path, default=Path("var/console"))
    web.add_argument("--web-root", type=Path, default=Path("src/web/dist"))
    web.add_argument("--task", type=Path, action="append", default=[])
    web.add_argument("--port", type=int, default=8765)
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
    task = commands.add_parser("task", help="Prepare and inspect task manifests")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    for name in ("validate", "view", "freeze"):
        entry = task_commands.add_parser(name)
        entry.add_argument("manifest")
    prepare = task_commands.add_parser("prepare")
    prepare.add_argument("manifest")
    prepare.add_argument("destination")
    resource_check = task_commands.add_parser("resource-check")
    resource_check.add_argument("manifest")
    resource_check.add_argument("request")
    draft = task_commands.add_parser("draft")
    draft.add_argument("instruction")
    draft.add_argument("--task-id", required=True)
    draft.add_argument("--data")
    draft.add_argument("--output", required=True)
    native = task_commands.add_parser("import-researchclaw")
    native.add_argument("workspace")
    native.add_argument("--native-id", required=True)
    native.add_argument("--source-revision", required=True)
    native.add_argument("--output", required=True)
    records = commands.add_parser("records", help="Inspect durable Run records and trajectories")
    records_commands = records.add_subparsers(dest="records_command", required=True)
    for name in ("run", "attempt", "events", "artifacts", "trajectory"):
        entry = records_commands.add_parser(name)
        entry.add_argument("identifier")
        entry.add_argument("--root", required=True)
        if name == "events":
            entry.add_argument("--limit", type=int, default=200)
    export = records_commands.add_parser("export")
    export.add_argument("identifiers", nargs="+")
    export.add_argument("--root", required=True)
    export.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    if args.command == "web":
        if web_action is None:
            parser.exit(2, "Web service is not configured\n")
        try:
            return web_action(
                args.records_root, args.console_dir, args.web_root, tuple(args.task), args.port
            )
        except (OSError, ValueError):
            parser.exit(2, "Web startup failed; check build directory, port and state paths\n")
    if args.command == "records":
        if records_action is None:
            parser.exit(2, "Records service is not configured\n")
        values = {
            key: value
            for key, value in vars(args).items()
            if key not in {"command", "records_command"} and value is not None
        }
        if isinstance(values.get("identifiers"), list):
            values["identifiers"] = json.dumps(values["identifiers"])
        try:
            result = records_action(
                args.records_command,
                {key: str(value) for key, value in values.items()},
            )
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            parser.exit(2, f"Records error: {error}\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "task":
        if task_action is None:
            parser.exit(2, "Task service is not configured\n")
        try:
            result = task_action(
                args.task_command,
                {
                    key: value
                    for key, value in vars(args).items()
                    if key not in {"command", "task_command"} and value is not None
                },
            )
        except (OSError, ValueError) as error:
            parser.exit(2, f"Task error: {error}\n")
        print(json.dumps(result, sort_keys=True))
        return 1 if result.get("status") == "needs_input" else 0
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
