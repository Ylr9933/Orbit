"""Verify the actual repository import policy rejects reverse coupling."""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("environments", "agents"),
        ("records", "runs"),
        ("resources", "bootstrap"),
        ("contracts", "tasks"),
        ("agents", "tasks"),
    ],
)
def test_reverse_dependency_is_rejected(tmp_path: Path, source: str, target: str) -> None:
    # A disposable package prevents mutating real source or relying on import caches.
    package = tmp_path / "agent_infra"
    shutil.copytree(ROOT / "src/agent_infra", package)
    (package / source / "violation.py").write_text(f"import agent_infra.{target}\n")
    project = (ROOT / "pyproject.toml").read_text()
    tomllib.loads(project)  # The fixture uses the actual policy, not a weaker copy.
    (tmp_path / "pyproject.toml").write_text(project)
    result = subprocess.run(
        ["lint-imports", "--no-cache"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BROKEN" in result.stdout
