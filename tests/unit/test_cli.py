"""Exercise the installed console entry point and its failure exit status."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from agent_infra.gateways.cli.main import run


def test_installed_cli_from_another_directory(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_INFRA_")}
    result = subprocess.run(
        ["agent-infra", "config-check"], cwd=tmp_path, env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state_dir"] == str(tmp_path / "var")
    assert not (tmp_path / "var").exists()


def test_cli_reports_configuration_error_without_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        ["agent-infra", "config-check", "--config", str(tmp_path / "missing.toml")],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "Configuration error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_agent_doctor_prints_machine_readable_probe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run(
        lambda path: {},
        lambda provider: {
            "provider": provider,
            "available": True,
            "authenticated": True,
            "container_auth_reusable": True,
        },
        lambda provider: {},
        ["agent", "doctor", "codex"],
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["provider"] == "codex"


def test_agent_doctor_accepts_provider_without_generic_auth_probe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run(
        lambda path: {},
        lambda provider: {
            "provider": provider,
            "available": True,
            "authenticated": None,
            "container_auth_reusable": False,
        },
        lambda provider: {},
        ["agent", "doctor", "dsh"],
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["provider"] == "dsh"


def test_agent_doctor_rejects_incompatible_provider(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run(
        lambda path: {},
        lambda provider: {
            "provider": provider,
            "available": True,
            "compatible": False,
            "authenticated": None,
        },
        lambda provider: {},
        ["agent", "doctor", "dsh"],
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out)["compatible"] is False
