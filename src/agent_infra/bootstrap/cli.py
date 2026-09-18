"""Console composition root."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any

from agent_infra.agents import AgentRegistry
from agent_infra.agents.claude_code import ClaudeCodeAdapter
from agent_infra.agents.codex import CodexAdapter
from agent_infra.agents.deepseek_harness import DeepSeekHarnessAdapter
from agent_infra.bootstrap.controller import run_action
from agent_infra.bootstrap.projects import project_action
from agent_infra.bootstrap.settings import load_settings
from agent_infra.bootstrap.web import serve_console
from agent_infra.gateways.cli.main import run
from agent_infra.records import AttemptTrajectoryBuilder, EventQuery, export_jsonl
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources import LinuxHostResourceMonitor, load_resource_request
from agent_infra.tasks import (
    build_agent_view,
    create_research_draft,
    freeze_task,
    load_task,
    materialize_agent_view,
    review_draft,
    validate_resource_plan,
    write_manifest,
)
from agent_infra.tasks.importers import import_researchclaw_workspace

_AGENTS = AgentRegistry(
    (CodexAdapter(), ClaudeCodeAdapter(), DeepSeekHarnessAdapter()),
    aliases={
        "claude": "claude-code",
        "claudecode": "claude-code",
        "deepseek": "dsh",
        "deepseek-harness": "dsh",
    },
)


def _check_config(path: Path | None) -> dict[str, str]:
    return {key: str(value) for key, value in asdict(load_settings(path)).items()}


def _probe_agent(provider: str) -> dict[str, object]:
    return asdict(_AGENTS.get(provider).probe())


def _setup_agent(provider: str) -> dict[str, object]:
    return asdict(_AGENTS.get(provider).ensure_installed())


def _inspect_resources() -> dict[str, object]:
    monitor = LinuxHostResourceMonitor()
    monitor.sample()
    sleep(0.1)
    return _json_mapping(asdict(monitor.sample()))


def _validate_resource_request(path: Path) -> dict[str, object]:
    return _json_mapping(asdict(load_resource_request(path)))


def _task_action(action: str, options: dict[str, str]) -> dict[str, object]:
    if action == "draft":
        task = create_research_draft(
            options["task_id"],
            Path(options["instruction"]),
            data=Path(options["data"]) if "data" in options else None,
        )
        write_manifest(task, Path(options["output"]))
        return _json_mapping(asdict(review_draft(task)))
    if action == "import-researchclaw":
        task = import_researchclaw_workspace(
            Path(options["workspace"]),
            native_id=options["native_id"],
            source_revision=options["source_revision"],
        )
        write_manifest(task, Path(options["output"]))
        return {"status": "indexed_only", "manifest": options["output"]}
    task = load_task(Path(options["manifest"]))
    if action == "validate":
        return _json_mapping(asdict(review_draft(task)))
    if action == "view":
        return _json_mapping(asdict(build_agent_view(task)))
    if action == "freeze":
        return _json_mapping(asdict(freeze_task(task)))
    if action == "prepare":
        return _json_mapping(
            asdict(
                materialize_agent_view(
                    task,
                    freeze_task(task),
                    Path(options["destination"]),
                )
            )
        )
    if action == "resource-check":
        return _json_mapping(asdict(validate_resource_plan(task, Path(options["request"]))))
    raise ValueError(f"Unknown task action: {action}")


def _records_action(action: str, options: dict[str, str]) -> dict[str, object]:
    store = LocalRecordsStore(Path(options["root"]))
    if action == "run":
        return _json_mapping(asdict(store.get_run(options["identifier"])))
    if action == "attempt":
        return _json_mapping(asdict(store.get_attempt(options["identifier"])))
    if action == "events":
        page = store.read_events(
            EventQuery(attempt_id=options["identifier"], limit=int(options["limit"]))
        )
        return _json_mapping(asdict(page))
    if action == "artifacts":
        return {
            "items": [
                _json_mapping(asdict(item)) for item in store.list_artifacts(options["identifier"])
            ]
        }
    builder = AttemptTrajectoryBuilder(store)
    if action == "trajectory":
        return _json_mapping(asdict(builder.build(options["identifier"])))
    if action == "export":
        identifiers = json.loads(options["identifiers"])
        if not isinstance(identifiers, list) or not all(
            isinstance(identifier, str) for identifier in identifiers
        ):
            raise ValueError("export identifiers must be strings")
        exported = export_jsonl(
            tuple(builder.build(identifier) for identifier in identifiers),
            Path(options["destination"]),
        )
        return _json_mapping(asdict(exported))
    raise ValueError(f"Unknown Records action: {action}")


def _json_mapping(value: dict[str, Any]) -> dict[str, object]:
    return {key: _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def main() -> int:
    return run(
        _check_config,
        _probe_agent,
        _setup_agent,
        _inspect_resources,
        _validate_resource_request,
        task_action=_task_action,
        records_action=_records_action,
        project_action=project_action,
        run_action=run_action,
        web_action=lambda records, console, web, tasks, port: serve_console(
            _AGENTS, records, console, web, tasks, port
        ),
    )
