"""Exercise the installed console entry point and its failure exit status."""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_infra.gateways.cli.main import run
from agent_infra.records import AttemptManifest, RunManifest
from agent_infra.records.local import LocalRecordsStore


def _no_resources() -> dict[str, object]:
    return {}


def _validate_resource(path: Path) -> dict[str, object]:
    return {"path": str(path)}


def test_installed_cli_from_another_directory(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_INFRA_")}
    env["XDG_STATE_HOME"] = str(tmp_path / "user-state")
    result = subprocess.run(
        ["agent-infra", "config-check"], cwd=tmp_path, env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state_dir"] == str(tmp_path / "user-state/agent-infra")
    assert not (tmp_path / "user-state").exists()


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
        _no_resources,
        _validate_resource,
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
        _no_resources,
        _validate_resource,
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
        _no_resources,
        _validate_resource,
        ["agent", "doctor", "dsh"],
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out)["compatible"] is False


def test_resource_validate_routes_the_yaml_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "resource.yaml"
    result = run(
        lambda path: {},
        lambda provider: {},
        lambda provider: {},
        _no_resources,
        _validate_resource,
        ["resource", "validate", str(request)],
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(request)}


def test_gpu_cli_routes_doctor_smoke_and_controller_allowlist(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen = []

    def gpu_action(action, args):
        seen.append((action, getattr(args, "gpu_uuid", None), getattr(args, "image", None)))
        return {"ready": action == "gpu-smoke"}

    callbacks = (
        lambda path: {},
        lambda provider: {},
        lambda provider: {},
        _no_resources,
        _validate_resource,
    )
    assert run(*callbacks, ["resource", "gpu-doctor"], gpu_action=gpu_action) == 1
    assert json.loads(capsys.readouterr().out)["ready"] is False
    assert (
        run(
            *callbacks,
            ["resource", "gpu-smoke", "--gpu-uuid", "GPU-one", "--image", "local:cuda"],
            gpu_action=gpu_action,
        )
        == 0
    )
    capsys.readouterr()
    assert seen == [("gpu-doctor", None, None), ("gpu-smoke", "GPU-one", "local:cuda")]

    def controller_action(args):
        assert args.gpu_uuid == ["GPU-one", "GPU-two"]
        return {"authorized_gpu_uuids": args.gpu_uuid}

    assert (
        run(
            *callbacks,
            ["controller", "serve", "--gpu-uuid", "GPU-one", "--gpu-uuid", "GPU-two"],
            run_action=controller_action,
        )
        == 0
    )


def test_task_cli_view_hides_private_materials() -> None:
    result = subprocess.run(
        ["agent-infra", "task", "view", "examples/task-packages/file-result/task.yaml"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    view = json.loads(result.stdout)
    assert {item["id"] for item in view["materials"]} == {"instruction", "input"}
    assert "expected" not in result.stdout
    assert "evaluator" not in result.stdout


def test_task_cli_draft_returns_actionable_clarifications(tmp_path: Path) -> None:
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Study the supplied research question")
    result = subprocess.run(
        [
            "agent-infra",
            "task",
            "draft",
            str(instruction),
            "--task-id",
            "new-task",
            "--output",
            str(tmp_path / "task.yaml"),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert (tmp_path / "task.yaml").exists()
    assert json.loads(result.stdout)["issues"][0]["code"] == "needs_output"


def test_records_cli_reads_durable_attempt(tmp_path: Path) -> None:
    root = tmp_path / "records"
    store = LocalRecordsStore(root)
    now = datetime.now(UTC)
    store.begin_run(RunManifest("run", now, {"kind": "test"}))
    store.begin_attempt(AttemptManifest("attempt", "run", now))
    store.finish_attempt("attempt", status="completed", result={"status": "completed"})
    store.finish_run("run", status="completed")
    result = subprocess.run(
        ["agent-infra", "records", "attempt", "attempt", "--root", str(root)],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["manifest"]["attempt_id"] == "attempt"
