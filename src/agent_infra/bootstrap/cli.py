"""Console composition root."""

from dataclasses import asdict
from pathlib import Path

from agent_infra.agents.codex import CodexAdapter
from agent_infra.bootstrap.settings import load_settings
from agent_infra.gateways.cli.main import run


def _check_config(path: Path | None) -> dict[str, str]:
    return {key: str(value) for key, value in asdict(load_settings(path)).items()}


def _probe_agent(provider: str) -> dict[str, object]:
    if provider != "codex":
        raise ValueError(f"Unsupported Agent provider: {provider}")
    return asdict(CodexAdapter().probe())


def _setup_agent(provider: str) -> dict[str, object]:
    if provider != "codex":
        raise ValueError(f"Unsupported Agent provider: {provider}")
    return asdict(CodexAdapter().ensure_installed())


def main() -> int:
    return run(_check_config, _probe_agent, _setup_agent)
