"""Reuse manifest sections for explicit research execution settings."""

from pathlib import Path
from typing import Any

from agent_infra.tasks.manifest import _read_yaml, _section, only_keys


def load_execution_settings(path: Path) -> dict[str, Any]:
    """Validate settings without starting an environment or inferring missing choices."""
    data = _read_yaml(path)
    names = ("environment", "tools", "evaluation", "execution_policy")
    only_keys(data, set(names), "execution settings")
    for name in names:
        _section(data.get(name, {"state": "unspecified"}), name)
    return data
