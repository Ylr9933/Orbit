"""Small S0 configuration surface; add backend settings with their implementation."""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_infra.bootstrap.paths import state_root


@dataclass(frozen=True)
class Settings:
    state_dir: Path
    log_level: str


def load_settings(path: Path | None = None, environ: Mapping[str, str] | None = None) -> Settings:
    """Validate configuration without creating directories or reading credentials."""
    env = os.environ if environ is None else environ
    values: dict[str, object] = {"state_dir": str(state_root(environ=env)), "log_level": "INFO"}
    if path is not None:
        with path.open("rb") as stream:
            supplied = tomllib.load(stream)
        unknown = supplied.keys() - values.keys()
        if unknown:
            raise ValueError("unknown configuration keys: " + ", ".join(sorted(unknown)))
        values.update(supplied)
    for key in values:
        env_key = f"AGENT_INFRA_{key.upper()}"
        if env_key in env:
            values[key] = env[env_key]
    state_value, log_level = values["state_dir"], values["log_level"]
    if not isinstance(state_value, str) or not state_value.strip():
        raise ValueError("state_dir must be a non-empty path string")
    if not isinstance(log_level, str) or log_level not in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }:
        raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    return Settings(state_dir=state_root(state_value, environ=env), log_level=log_level)
