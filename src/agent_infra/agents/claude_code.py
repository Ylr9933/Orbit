"""Claude Code CLI adapter for host and isolated container runs."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from agent_infra.agents._cli_support import (
    CommandRunner,
    ensure_npm_cli,
    probe_npm_cli,
    run_command,
    stage_private_files,
)
from agent_infra.agents.api import (
    AgentCapability,
    AgentDescriptor,
    AgentEvent,
    AgentEventKind,
    AgentLaunchPlan,
    AgentPermissionMode,
    AgentPlacement,
    AgentProbe,
    AgentRunRequest,
    BindMount,
)

CLAUDE_PROVIDER = "claude-code"
CLAUDE_NPM_PACKAGE = "@anthropic-ai/claude-code"
DEFAULT_CLAUDE_IMAGE = "agent-infra/claude-code-cli:2.1.272"
CONTAINER_CLAUDE_HOME = "/home/agent/.claude"
CONTAINER_WORKSPACE = "/workspace"
CLAUDE_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


class ClaudeCodeAdapter:
    """Translate common Agent requests into Claude Code print-mode plans."""

    def __init__(
        self,
        *,
        binary: str = "claude",
        container_image: str = DEFAULT_CLAUDE_IMAGE,
        runner: CommandRunner = run_command,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._binary = binary
        self._container_image = container_image
        self._runner = runner
        self._environ = os.environ if environ is None else environ

    @property
    def descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            provider=CLAUDE_PROVIDER,
            display_name="Anthropic Claude Code",
            integration="cli",
            capabilities=frozenset(
                {
                    AgentCapability.NON_INTERACTIVE,
                    AgentCapability.RESUME,
                    AgentCapability.EVENT_STREAM,
                    AgentCapability.HOST_EXECUTION,
                    AgentCapability.CONTAINER_EXECUTION,
                }
            ),
        )

    @property
    def host_claude_home(self) -> Path:
        configured = self._environ.get("CLAUDE_CONFIG_DIR")
        if configured:
            return Path(configured).expanduser()
        configured_home = self._environ.get("HOME")
        return (Path(configured_home) if configured_home else Path.home()) / ".claude"

    def probe(self) -> AgentProbe:
        credential = self.host_claude_home / ".credentials.json"
        return probe_npm_cli(
            provider=CLAUDE_PROVIDER,
            binary=self._binary,
            npm_package=CLAUDE_NPM_PACKAGE,
            runner=self._runner,
            auth_args=("auth", "status"),
            container_config_reusable=credential.is_file() and not credential.is_symlink(),
        )

    def ensure_installed(self) -> AgentProbe:
        return ensure_npm_cli(self.probe, self._runner)

    def stage_container_credentials(self, destination: Path) -> Path:
        return stage_private_files(
            source_home=self.host_claude_home,
            destination=destination,
            filenames=(".credentials.json",),
        )

    def create_launch_plan(
        self, request: AgentRunRequest, *, credential_home: Path | None = None
    ) -> AgentLaunchPlan:
        _validate_request(request)
        runtime_workspace = (
            CONTAINER_WORKSPACE
            if request.placement is AgentPlacement.CONTAINER
            else str(request.workspace.resolve())
        )
        binary = "claude" if request.placement is AgentPlacement.CONTAINER else self._binary
        argv = [binary, "--print", "--output-format", "stream-json", "--verbose"]
        if request.model:
            argv.extend(["--model", request.model])
        if request.reasoning_effort:
            argv.extend(["--effort", request.reasoning_effort])
        if request.resume_session_id:
            argv.extend(["--resume", request.resume_session_id])

        mounts: tuple[BindMount, ...] = ()
        environment: tuple[tuple[str, str], ...] = ()
        image: str | None = None
        if request.placement is AgentPlacement.CONTAINER:
            if credential_home is None:
                raise ValueError("container placement requires an isolated credential_home")
            if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX:
                argv.extend(["--permission-mode", "bypassPermissions"])
            else:
                argv.extend(["--permission-mode", "acceptEdits"])
            argv.extend(["--safe-mode", "--strict-mcp-config"])
            environment = (
                ("HOME", "/home/agent"),
                ("CLAUDE_CONFIG_DIR", CONTAINER_CLAUDE_HOME),
            )
            mounts = (
                BindMount(credential_home.resolve(), CONTAINER_CLAUDE_HOME, read_only=False),
                BindMount(request.workspace.resolve(), CONTAINER_WORKSPACE, read_only=False),
            )
            image = self._container_image
        else:
            if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX:
                raise ValueError("outer_sandbox permission mode is valid only inside a container")
            argv.extend(["--permission-mode", "acceptEdits"])

        return AgentLaunchPlan(
            provider=CLAUDE_PROVIDER,
            placement=request.placement,
            argv=tuple(argv),
            cwd=runtime_workspace,
            stdin_text=request.prompt,
            environment=environment,
            mounts=mounts,
            container_image=image,
        )

    def decode_events(self, lines: Iterator[str]) -> Iterator[AgentEvent]:
        for sequence, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                yield AgentEvent(sequence, AgentEventKind.ERROR, "invalid_json", {"text": stripped})
                continue
            if not isinstance(payload, dict):
                yield AgentEvent(sequence, AgentEventKind.UNKNOWN, "unknown", {"value": payload})
                continue
            native_type = str(payload.get("type", "unknown"))
            yield AgentEvent(
                sequence, _claude_event_kind(native_type, payload), native_type, payload
            )


def _validate_request(request: AgentRunRequest) -> None:
    if not request.run_id.strip():
        raise ValueError("run_id must not be empty")
    if not request.prompt.strip():
        raise ValueError("prompt must not be empty")
    if request.reasoning_effort is not None and request.reasoning_effort not in CLAUDE_EFFORTS:
        supported = ", ".join(sorted(CLAUDE_EFFORTS))
        raise ValueError(f"unsupported Claude Code effort; choose one of: {supported}")


def _claude_event_kind(native_type: str, payload: dict[str, object]) -> AgentEventKind:
    if native_type == "system":
        return AgentEventKind.SESSION
    if native_type == "result":
        return AgentEventKind.ERROR if payload.get("is_error") is True else AgentEventKind.COMPLETED
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    blocks = content if isinstance(content, list) else []
    block_types = {str(block.get("type", "")) for block in blocks if isinstance(block, dict)}
    if "tool_result" in block_types:
        return AgentEventKind.TOOL_RESULT
    if "tool_use" in block_types:
        return AgentEventKind.TOOL_CALL
    if native_type in {"assistant", "user"}:
        return AgentEventKind.MESSAGE
    return AgentEventKind.UNKNOWN
