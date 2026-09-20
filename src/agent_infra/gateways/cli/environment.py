"""Environment commands use the same project binding and controller as research MCP."""

import argparse
from pathlib import Path
from typing import Any

import yaml

from agent_infra.gateways.cli.research_runtime import ResearchClient


def add_environment_arguments(commands: Any) -> None:
    parser = commands.add_parser("environment", help="Plan, build and validate Python CPU images")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "propose", "build", "status", "cancel", "list"):
        item = actions.add_parser(action)
        item.add_argument("--state-dir")
        item.add_argument("--project-id", required=True)
        item.add_argument("--session-id", default="cli")
        if action not in {"status", "list"}:
            item.add_argument("--operation-id", required=True)
        if action not in {"plan", "list"}:
            item.add_argument("plan_id")
        if action in {"plan", "propose"}:
            item.add_argument(
                "--file", type=Path, required=True, help="Explicit intent/proposal YAML"
            )
        if action == "propose":
            item.add_argument("--expected-revision", type=int, required=True)
        if action == "build":
            item.add_argument("--revision", type=int, required=True)
        if action == "status":
            item.add_argument("--attempt-id")
            item.add_argument("--cursor", type=int, default=0)


def environment_client(state: Path, args: argparse.Namespace) -> dict[str, Any]:
    client = ResearchClient(state, args.project_id, args.session_id)
    options = {
        k: v
        for k, v in vars(args).items()
        if k
        not in {
            "command",
            "action",
            "state_dir",
            "project_id",
            "session_id",
            "operation_id",
            "file",
        }
        and v is not None
    }
    if args.action in {"plan", "propose"}:
        if args.file.stat().st_size > 32768:
            raise ValueError("environment document exceeds 32 KiB")
        options["intent" if args.action == "plan" else "proposal"] = yaml.safe_load(
            args.file.read_text()
        )
    return client.call(
        "environment_" + args.action, operation_id=getattr(args, "operation_id", None), **options
    )
