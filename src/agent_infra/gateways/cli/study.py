"""Thin CLI for analysis, user decisions and bounded research workflows."""

import argparse
import json
from pathlib import Path
from typing import Any

from agent_infra.gateways.cli.research_runtime import ResearchClient


def add_study_arguments(commands: Any) -> None:
    parser = commands.add_parser(
        "study", help="Evidence analysis, decisions and authorized iteration"
    )
    actions = parser.add_subparsers(dest="action", required=True)
    for name in (
        "analysis-save",
        "analyses",
        "decide",
        "decisions",
        "authorize",
        "workflows",
        "status",
        "step",
        "stop",
        "read",
    ):
        entry = actions.add_parser(name)
        entry.add_argument("--state-dir")
        entry.add_argument("--project-id", required=True)
        entry.add_argument("--session-id", default="cli")
        if name in {"analysis-save", "decide", "authorize", "step"}:
            entry.add_argument("--operation-id", required=True)
        if name in {"analysis-save", "decide", "authorize"}:
            entry.add_argument("--file", type=Path, required=True, help="UTF-8 JSON document")
        if name in {"status", "step", "stop", "read"}:
            entry.add_argument("--workflow-id", required=True)
        if name == "step":
            entry.add_argument("--task-key", required=True)
        if name == "stop":
            entry.add_argument("--reason", required=True)
        if name == "read":
            entry.add_argument("--run-id", required=True)
            entry.add_argument("--artifact-id")
            entry.add_argument("--member")


def study_client(state: Path, args: argparse.Namespace) -> dict[str, Any]:
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
    if getattr(args, "file", None):
        with args.file.open("rb") as source:
            data = source.read(60001)
        if len(data) > 60000:
            raise ValueError("study document exceeds 60000-byte transport limit")
        options["document"] = json.loads(data)
    return ResearchClient(state, args.project_id, args.session_id).call(
        "study_" + args.action.replace("-", "_"),
        operation_id=getattr(args, "operation_id", None),
        **options,
    )


def add_planner_arguments(commands: Any) -> None:
    parser = commands.add_parser(
        "planner", help="Disposable Codex Planner bound to an authorized workflow"
    )
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "status", "stop"):
        entry = actions.add_parser(name)
        entry.add_argument("--state-dir")
        entry.add_argument("--project-id", required=True)
        if name != "start":
            entry.add_argument("--run-id", required=True)
        else:
            entry.add_argument("--workflow-id", required=True)
            entry.add_argument("--operation-id", required=True)
            entry.add_argument("--image", required=True)
            entry.add_argument("--model", required=True)
            entry.add_argument("--timeout-seconds", type=float, default=300)
            entry.add_argument("--cpu", type=float, default=0.25)
            entry.add_argument("--memory-bytes", type=int, default=512 * 1024**2)
            entry.add_argument(
                "--prompt", default="Continue authorized experiments and analyze results."
            )


def planner_client(state: Path, args: argparse.Namespace) -> dict[str, Any]:
    from agent_infra.gateways.cli.runs import ControllerClient

    options = {
        k: v
        for k, v in vars(args).items()
        if k not in {"state_dir", "command", "project_id", "action", "operation_id"}
    }
    return ControllerClient(state).request(
        "planner/" + args.action,
        {
            "project_id": args.project_id,
            "options": options,
            "operation_id": getattr(args, "operation_id", None),
        },
    )
