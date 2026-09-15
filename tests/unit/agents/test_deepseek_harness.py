"""DeepSeek Harness adapter contract and event normalization tests."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agent_infra.agents import AgentEventKind, AgentPlacement, AgentRunRequest
from agent_infra.agents.deepseek_harness import DeepSeekHarnessAdapter


def _completed(argv: list[str], returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def test_probe_reports_configuration_without_claiming_generic_auth(tmp_path: Path) -> None:
    dsh_home = tmp_path / ".dsh"
    dsh_home.mkdir()
    (dsh_home / "settings.yaml").write_text("activeProfile: default")
    (dsh_home / ".credentials.yaml").write_text("credential refs")

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _completed(argv, 0, "0.1.6-alpha.1")

    probe = DeepSeekHarnessAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"DSH_HOME": str(dsh_home)},
    ).probe()

    assert probe.available is True
    assert probe.version == "0.1.6-alpha.1"
    assert probe.authenticated is None
    assert probe.container_auth_reusable is True
    assert any("no side-effect-free" in issue for issue in probe.issues)


def test_staging_copies_only_settings_and_credentials(tmp_path: Path) -> None:
    dsh_home = tmp_path / ".dsh"
    dsh_home.mkdir()
    (dsh_home / "settings.yaml").write_text("model config")
    (dsh_home / ".credentials.yaml").write_text("credential refs")
    (dsh_home / "sessions.json").write_text("private history")
    destination = tmp_path / "run" / "dsh-home"

    DeepSeekHarnessAdapter(environ={"DSH_HOME": str(dsh_home)}).stage_container_credentials(
        destination
    )

    assert (destination / "settings.yaml").read_text() == "model config"
    assert (destination / ".credentials.yaml").read_text() == "credential refs"
    assert not (destination / "sessions.json").exists()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE((destination / "settings.yaml").stat().st_mode) == 0o600
    assert stat.S_IMODE((destination / ".credentials.yaml").stat().st_mode) == 0o600


def test_host_plan_uses_headless_json_and_stdin(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="dsh-research",
        prompt="Run the experiment",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        resume_session_id="session-2",
    )

    plan = DeepSeekHarnessAdapter(binary="/usr/local/bin/dsh").create_launch_plan(request)

    assert plan.argv == (
        "/usr/local/bin/dsh",
        "--profile",
        "headless",
        "--json",
        "--session-id",
        "session-2",
    )
    assert plan.stdin_text == request.prompt
    assert plan.container_image is None


def test_container_plan_uses_private_home(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="dsh-benchmark",
        prompt="Solve",
        workspace=tmp_path / "workspace",
        placement=AgentPlacement.CONTAINER,
    )

    plan = DeepSeekHarnessAdapter().create_launch_plan(
        request, credential_home=tmp_path / "credentials"
    )

    assert plan.argv[:4] == ("dsh", "--profile", "headless", "--json")
    assert plan.environment_dict()["DSH_HOME"] == "/home/agent/.dsh"
    assert [mount.target for mount in plan.mounts] == ["/home/agent/.dsh", "/workspace"]
    assert plan.container_image == "agent-infra/deepseek-harness:0.1.6-alpha.1"


def test_probe_marks_old_headless_protocol_incompatible(tmp_path: Path) -> None:
    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _completed(argv, 0, "0.1.5-rc.1")

    probe = DeepSeekHarnessAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"DSH_HOME": str(tmp_path)},
    ).probe()

    assert probe.available is True
    assert probe.compatible is False
    assert any("JSON events" in issue for issue in probe.issues)


def test_setup_upgrades_old_dsh_to_required_headless_protocol(tmp_path: Path) -> None:
    version = "0.1.5-rc.1"
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal version
        calls.append(tuple(argv))
        if argv[0] == "npm":
            version = "0.1.6-alpha.1"
            return _completed(argv, 0, "")
        return _completed(argv, 0, version)

    probe = DeepSeekHarnessAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"DSH_HOME": str(tmp_path)},
    ).ensure_installed()

    assert probe.compatible is True
    assert (
        "npm",
        "install",
        "--global",
        "@deepseek-ai/dsh@0.1.6-alpha.1",
    ) in calls


def test_per_run_model_override_is_rejected(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="dsh-model",
        prompt="Run",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        model="deepseek-chat",
    )

    with pytest.raises(ValueError, match="active profile"):
        DeepSeekHarnessAdapter().create_launch_plan(request)


def test_events_normalize_documented_headless_types() -> None:
    native_types = [
        "session",
        "text",
        "tool_call",
        "tool_result",
        "status",
        "final",
        "error",
    ]
    lines = iter(
        '{"type":"' + native_type + '","usage":{"tokens":1}}' for native_type in native_types
    )

    events = list(DeepSeekHarnessAdapter().decode_events(lines))

    assert [event.kind for event in events] == [
        AgentEventKind.SESSION,
        AgentEventKind.MESSAGE,
        AgentEventKind.TOOL_CALL,
        AgentEventKind.TOOL_RESULT,
        AgentEventKind.USAGE,
        AgentEventKind.COMPLETED,
        AgentEventKind.ERROR,
    ]
