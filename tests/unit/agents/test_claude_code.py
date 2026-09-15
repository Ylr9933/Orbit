"""Claude Code adapter contract, isolation and event normalization tests."""

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
from agent_infra.agents.claude_code import ClaudeCodeAdapter


def _completed(argv: list[str], returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def test_probe_reports_auth_but_requires_file_credentials_for_container(
    tmp_path: Path,
) -> None:
    claude_home = tmp_path / ".claude"
    claude_home.mkdir()

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        output = "2.1.272 (Claude Code)" if argv[-1] == "--version" else "private account"
        return _completed(argv, 0, output)

    probe = ClaudeCodeAdapter(
        binary=sys.executable,
        runner=runner,
        environ={"CLAUDE_CONFIG_DIR": str(claude_home)},
    ).probe()

    assert probe.available is True
    assert probe.version == "2.1.272"
    assert probe.authenticated is True
    assert probe.container_auth_reusable is False
    assert "private account" not in repr(probe)


def test_staged_credentials_exclude_user_settings(tmp_path: Path) -> None:
    claude_home = tmp_path / ".claude"
    claude_home.mkdir()
    (claude_home / ".credentials.json").write_text("credential")
    (claude_home / "settings.json").write_text("personal settings")
    destination = tmp_path / "run" / "claude-home"

    ClaudeCodeAdapter(environ={"CLAUDE_CONFIG_DIR": str(claude_home)}).stage_container_credentials(
        destination
    )

    assert (destination / ".credentials.json").read_text() == "credential"
    assert not (destination / "settings.json").exists()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE((destination / ".credentials.json").stat().st_mode) == 0o600


def test_host_plan_uses_print_mode_and_structured_options(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="claude-research",
        prompt="Run the experiment",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        model="sonnet",
        reasoning_effort="high",
        resume_session_id="session-1",
    )

    plan = ClaudeCodeAdapter(binary="/usr/local/bin/claude").create_launch_plan(request)

    assert plan.argv[:5] == (
        "/usr/local/bin/claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
    )
    assert ("--model", "sonnet") == plan.argv[5:7]
    assert ("--resume", "session-1") == plan.argv[9:11]
    assert plan.stdin_text == request.prompt
    assert plan.container_image is None


def test_container_plan_uses_private_home_and_outer_sandbox(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="claude-benchmark",
        prompt="Solve the benchmark",
        workspace=tmp_path / "workspace",
        placement=AgentPlacement.CONTAINER,
        permission_mode=AgentPermissionMode.OUTER_SANDBOX,
    )

    plan = ClaudeCodeAdapter().create_launch_plan(request, credential_home=tmp_path / "credentials")

    assert plan.argv[0] == "claude"
    assert ("--permission-mode", "bypassPermissions") == plan.argv[-4:-2]
    assert "--safe-mode" in plan.argv
    assert plan.environment_dict()["CLAUDE_CONFIG_DIR"] == "/home/agent/.claude"
    assert [mount.target for mount in plan.mounts] == ["/home/agent/.claude", "/workspace"]
    assert plan.container_image == "agent-infra/claude-code-cli:2.1.272"


def test_outer_sandbox_is_rejected_on_host(tmp_path: Path) -> None:
    request = AgentRunRequest(
        run_id="claude-host",
        prompt="Run",
        workspace=tmp_path,
        placement=AgentPlacement.HOST,
        permission_mode=AgentPermissionMode.OUTER_SANDBOX,
    )

    with pytest.raises(ValueError, match="only inside a container"):
        ClaudeCodeAdapter().create_launch_plan(request)


def test_events_preserve_native_payload_and_normalize_tool_blocks() -> None:
    lines = iter(
        [
            '{"type":"system","session_id":"abc"}',
            '{"type":"assistant","message":{"content":[{"type":"tool_use"}]}}',
            '{"type":"user","message":{"content":[{"type":"tool_result"}]}}',
            '{"type":"result","is_error":false}',
        ]
    )

    events = list(ClaudeCodeAdapter().decode_events(lines))

    assert [event.kind for event in events] == [
        AgentEventKind.SESSION,
        AgentEventKind.TOOL_CALL,
        AgentEventKind.TOOL_RESULT,
        AgentEventKind.COMPLETED,
    ]
    assert events[0].payload["session_id"] == "abc"
