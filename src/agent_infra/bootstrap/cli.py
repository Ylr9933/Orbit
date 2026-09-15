"""Console composition root."""

from dataclasses import asdict
from pathlib import Path

from agent_infra.bootstrap.settings import load_settings
from agent_infra.gateways.cli.main import run


def _check_config(path: Path | None) -> dict[str, str]:
    return {key: str(value) for key, value in asdict(load_settings(path)).items()}


def main() -> int:
    return run(_check_config)
