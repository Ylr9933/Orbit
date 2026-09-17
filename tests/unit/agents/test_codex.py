"""Codex adapter contract, isolation and event normalization tests."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agent_infra.agents import (
    AgentEventKind,
    AgentPermissionMode,
    AgentPlacement,
    AgentRunRequest,
)
from agent_infra.agents.codex import CodexAdapter


def _completed(argv: list[str], returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def test_probe_reports_version_and_file_auth_without_returning_command_output(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("secret-value")

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if argv[-1] == "--version":
            return _completed(argv, 0, "codex-cli 0.154.0\n")
        return _completed(argv, 0, "Logged in as private@example.com\n")

    probe = CodexAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"CODEX_HOME": str(codex_home)},
    ).probe()

    assert probe.available is True
    assert probe.version == "0.154.0"
    assert probe.authenticated is True
    assert probe.container_auth_reusable is True
    assert "private@example.com" not in repr(probe)
    assert "secret-value" not in repr(probe)


def test_missing_codex_returns_an_actionable_install_command() -> None:
    probe = CodexAdapter(binary="agent-infra-codex-does-not-exist").probe()

    assert probe.available is False
    assert probe.authenticated is None
    assert probe.install_command == ("npm", "install", "--global", "@openai/codex")


def test_setup_does_not_reinstall_an_available_codex(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        stdout = "codex-cli 0.154.0" if argv[-1] == "--version" else ""
        return _completed(argv, 0, stdout)

    probe = CodexAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"CODEX_HOME": str(codex_home)},
    ).ensure_installed()

    assert probe.available is True
    assert all("install" not in call for call in calls)


def test_setup_installs_the_official_package_when_codex_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discoveries = iter([None, "/installed/codex"])
    monkeypatch.setattr(
        "agent_infra.agents._cli_support.shutil.which", lambda binary: next(discoveries)
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        stdout = "codex-cli 0.154.0" if argv[-1] == "--version" else ""
        return _completed(argv, 0, stdout)

    probe = CodexAdapter(runner=runner).ensure_installed()

    assert probe.available is True
    assert ("npm", "install", "--global", "@openai/codex") in calls


def test_staged_credentials_copy_only_auth_with_private_permissions(tmp_path: Path) -> None:
    host_home = tmp_path / "host-codex"
    host_home.mkdir()
    (host_home / "auth.json").write_text("credentials")
    (host_home / "config.toml").write_text("untrusted = true")
    destination = tmp_path / "run" / "codex-home"
    adapter = CodexAdapter(environ={"CODEX_HOME": str(host_home)})

    assert adapter.stage_container_credentials(destination) == destination

    assert (destination / "auth.json").read_text() == "credentials"
    assert not (destination / "config.toml").exists()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE((destination / "auth.json").stat().st_mode) == 0o600


def test_staging_rejects_a_symlinked_destination(tmp_path: Path) -> None:
    host_home = tmp_path / "host-codex"
    host_home.mkdir()
    (host_home / "auth.json").write_text("credentials")
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        CodexAdapter(environ={"CODEX_HOME": str(host_home)}).stage_container_credentials(linked)


def test_host_plan_keeps_host_configuration_and_passes_prompt_over_stdin(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="research-1",
        prompt="Run the training script",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        model="gpt-test",
        reasoning_effort="medium",
    )

    plan = CodexAdapter(binary="/usr/local/bin/codex").create_launch_plan(request)

    assert plan.argv[:2] == ("/usr/local/bin/codex", "exec")
    assert plan.argv[-2:] == ("--", "-")
    assert plan.stdin_text == request.prompt
    assert "--sandbox" in plan.argv
    assert "--ignore-user-config" not in plan.argv
    assert plan.container_image is None
    assert plan.mounts == ()


def test_container_plan_uses_isolated_home_and_outer_sandbox(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    credentials = tmp_path / "credentials"
    request = AgentRunRequest(
        run_id="benchmark-1",
        prompt="Solve the task",
        workspace=workspace,
        placement=AgentPlacement.CONTAINER,
        permission_mode=AgentPermissionMode.OUTER_SANDBOX,
    )

    plan = CodexAdapter().create_launch_plan(request, credential_home=credentials)

    assert plan.argv[:2] == ("codex", "exec")
    assert "--dangerously-bypass-approvals-and-sandbox" in plan.argv
    assert "--ignore-user-config" in plan.argv
    assert plan.environment_dict() == {"CODEX_HOME": "/home/agent/.codex"}
    assert [mount.target for mount in plan.mounts] == ["/home/agent/.codex", "/workspace"]
    assert plan.container_image == "agent-infra/codex-cli:0.154.0"


def test_outer_sandbox_cannot_be_selected_for_host_execution(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="unsafe-host",
        prompt="Run",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        permission_mode=AgentPermissionMode.OUTER_SANDBOX,
    )

    with pytest.raises(ValueError, match="only inside a container"):
        CodexAdapter().create_launch_plan(request)


def test_resume_is_rejected_until_its_distinct_cli_options_are_supported(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="resume-1",
        prompt="Continue",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        resume_session_id="session-id",
    )

    with pytest.raises(ValueError, match="resume is not implemented"):
        CodexAdapter().create_launch_plan(request)


def test_jsonl_events_preserve_native_payload_and_normalize_common_kinds() -> None:
    lines = iter(
        [
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"item.completed","item":{"type":"command_execution",'
            '"id":"call-1","command":"pytest","aggregated_output":"2 passed",'
            '"exit_code":0}}',
            '{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}',
            "not-json",
        ]
    )

    events = list(CodexAdapter().decode_events(lines))

    assert [event.kind for event in events] == [
        AgentEventKind.SESSION,
        AgentEventKind.TOOL_RESULT,
        AgentEventKind.COMPLETED,
        AgentEventKind.USAGE,
        AgentEventKind.ERROR,
    ]
    assert events[0].payload["thread_id"] == "abc"
    assert events[0].canonical == {"session_id": "abc"}
    assert events[1].canonical == {
        "tool_type": "command",
        "tool_call_id": "call-1",
        "tool_name": "shell",
        "arguments": {"command": "pytest"},
        "result": "2 passed",
        "is_error": False,
        "status": "succeeded",
    }
    assert events[3].canonical == {
        "input_tokens": 2,
        "output_tokens": 3,
        "total_tokens": 5,
    }
    assert events[2].native_sequence == events[3].native_sequence == 2
    assert (events[2].part_index, events[3].part_index) == (0, 1)
    assert events[-1].native_type == "invalid_json"
