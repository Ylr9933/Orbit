"""Console composition root."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any

from agent_infra.agents import AgentRegistry
from agent_infra.agents.claude_code import ClaudeCodeAdapter
from agent_infra.agents.codex import CodexAdapter
from agent_infra.agents.deepseek_harness import DeepSeekHarnessAdapter
from agent_infra.bootstrap.settings import load_settings
from agent_infra.gateways.cli.main import run
from agent_infra.resources import LinuxHostResourceMonitor, load_resource_request

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


def _json_mapping(value: dict[str, Any]) -> dict[str, object]:
    return {key: _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def main() -> int:
    return run(
        _check_config,
        _probe_agent,
        _setup_agent,
        _inspect_resources,
        _validate_resource_request,
    )
