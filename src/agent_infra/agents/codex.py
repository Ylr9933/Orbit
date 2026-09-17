"""Codex CLI adapter for host research and isolated container runs."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

from agent_infra.agents._cli_support import (
    CommandRunner,
    ensure_npm_cli,
    probe_npm_cli,
    run_command,
    stage_private_files,
)
from agent_infra.agents._event_normalization import (
    as_mapping,
    error_payload,
    first_string,
    first_value,
    structured_value,
    text_value,
    usage_payload,
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

CODEX_PROVIDER = "codex"
DEFAULT_CODEX_IMAGE = "agent-infra/codex-cli:0.154.0"
CONTAINER_CODEX_HOME = "/home/agent/.codex"
CONTAINER_WORKSPACE = "/workspace"
CODEX_NPM_PACKAGE = "@openai/codex"
CODEX_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "ultra"})


class CodexAdapter:
    """Translate provider-neutral requests into Codex CLI process plans."""

    def __init__(
        self,
        *,
        binary: str = "codex",
        container_image: str = DEFAULT_CODEX_IMAGE,
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
            provider=CODEX_PROVIDER,
            display_name="OpenAI Codex CLI",
            integration="cli",
            capabilities=frozenset(
                {
                    AgentCapability.NON_INTERACTIVE,
                    AgentCapability.EVENT_STREAM,
                    AgentCapability.HOST_EXECUTION,
                    AgentCapability.CONTAINER_EXECUTION,
                }
            ),
        )

    def probe(self) -> AgentProbe:
        auth_file = self.host_codex_home / "auth.json"
        return probe_npm_cli(
            provider=CODEX_PROVIDER,
            binary=self._binary,
            npm_package=CODEX_NPM_PACKAGE,
            runner=self._runner,
            auth_args=("login", "status"),
            container_config_reusable=auth_file.is_file() and not auth_file.is_symlink(),
        )

    def ensure_installed(self) -> AgentProbe:
        """Install the official npm package only when Codex is absent."""

        return ensure_npm_cli(self.probe, self._runner)

    @property
    def host_codex_home(self) -> Path:
        configured = self._environ.get("CODEX_HOME")
        if configured:
            return Path(configured).expanduser()
        configured_home = self._environ.get("HOME")
        return (Path(configured_home) if configured_home else Path.home()) / ".codex"

    def stage_container_credentials(self, destination: Path) -> Path:
        """Copy only file-based auth into a task-owned Codex home."""

        return stage_private_files(
            source_home=self.host_codex_home,
            destination=destination,
            filenames=("auth.json",),
        )

    def create_launch_plan(
        self, request: AgentRunRequest, *, credential_home: Path | None = None
    ) -> AgentLaunchPlan:
        if not request.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not request.prompt.strip():
            raise ValueError("prompt must not be empty")
        if request.resume_session_id is not None:
            raise ValueError("Codex session resume is not implemented by this adapter")
        if (
            request.reasoning_effort is not None
            and request.reasoning_effort not in CODEX_REASONING_EFFORTS
        ):
            supported = ", ".join(sorted(CODEX_REASONING_EFFORTS))
            raise ValueError(f"unsupported Codex reasoning effort; choose one of: {supported}")
        if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX and (
            request.placement is not AgentPlacement.CONTAINER
        ):
            raise ValueError("outer_sandbox permission mode is valid only inside a container")

        runtime_workspace = (
            CONTAINER_WORKSPACE
            if request.placement is AgentPlacement.CONTAINER
            else str(request.workspace.resolve())
        )
        binary = "codex" if request.placement is AgentPlacement.CONTAINER else self._binary
        argv = [binary, "exec"]
        if request.model:
            argv.extend(["--model", request.model])
        if request.reasoning_effort:
            argv.extend(["--config", f'model_reasoning_effort="{request.reasoning_effort}"'])
        argv.extend(
            [
                "--cd",
                runtime_workspace,
                "--skip-git-repo-check",
                "--json",
                "--color",
                "never",
            ]
        )

        mounts: tuple[BindMount, ...] = ()
        environment: tuple[tuple[str, str], ...] = ()
        image: str | None = None
        if request.placement is AgentPlacement.CONTAINER:
            if credential_home is None:
                raise ValueError("container placement requires an isolated credential_home")
            if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX:
                argv.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                argv.extend(["--sandbox", "workspace-write"])
            argv.extend(["--ignore-user-config", "--ignore-rules"])
            environment = (("CODEX_HOME", CONTAINER_CODEX_HOME),)
            mounts = (
                BindMount(credential_home.resolve(), CONTAINER_CODEX_HOME, read_only=False),
                BindMount(request.workspace.resolve(), CONTAINER_WORKSPACE, read_only=False),
            )
            image = self._container_image
        else:
            argv.extend(["--sandbox", "workspace-write"])

        argv.extend(["--", "-"])
        return AgentLaunchPlan(
            provider=CODEX_PROVIDER,
            placement=request.placement,
            argv=tuple(argv),
            cwd=runtime_workspace,
            stdin_text=request.prompt,
            environment=environment,
            mounts=mounts,
            container_image=image,
        )

    def decode_events(self, lines: Iterator[str]) -> Iterator[AgentEvent]:
        sequence = 0
        for native_sequence, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                yield AgentEvent(
                    sequence,
                    AgentEventKind.ERROR,
                    "invalid_json",
                    {"text": stripped},
                    {"error_type": "invalid_json", "message": stripped},
                    native_sequence=native_sequence,
                )
                sequence += 1
                continue
            if not isinstance(payload, dict):
                yield AgentEvent(
                    sequence,
                    AgentEventKind.UNKNOWN,
                    "unknown",
                    {"value": payload},
                    native_sequence=native_sequence,
                )
                sequence += 1
                continue
            native_type = str(payload.get("type", "unknown"))
            parts = _codex_event_parts(native_type, payload)
            for part_index, (kind, canonical) in enumerate(parts):
                yield AgentEvent(
                    sequence,
                    kind,
                    native_type,
                    payload,
                    canonical,
                    native_sequence=native_sequence,
                    part_index=part_index,
                )
                sequence += 1


def _codex_event_parts(
    native_type: str, payload: dict[str, object]
) -> list[tuple[AgentEventKind, dict[str, object]]]:
    kind = _event_kind(native_type, payload)
    parts: list[tuple[AgentEventKind, dict[str, object]]] = []
    item = as_mapping(payload.get("item"))
    item_type = first_string(item, "type")
    if kind is AgentEventKind.SESSION:
        session_id = first_string(payload, "thread_id", "session_id", "id")
        parts.append((kind, {"session_id": session_id} if session_id else {}))
    elif kind in {AgentEventKind.TOOL_CALL, AgentEventKind.TOOL_RESULT}:
        parts.append((kind, _codex_tool_payload(payload, item, item_type, kind)))
    elif kind is AgentEventKind.MESSAGE:
        text = text_value(first_value(item, "text", "content", "message"))
        canonical: dict[str, object] = {"role": "assistant"}
        if text is not None:
            canonical["text"] = text
        parts.append((kind, canonical))
    elif kind is AgentEventKind.COMPLETED:
        canonical = {}
        session_id = first_string(payload, "thread_id", "session_id")
        finish_reason = first_string(payload, "finish_reason", "status")
        if session_id is not None:
            canonical["session_id"] = session_id
        if finish_reason is not None:
            canonical["finish_reason"] = finish_reason
        parts.append((kind, canonical))
    elif kind is AgentEventKind.ERROR:
        parts.append((kind, error_payload(payload)))
    elif kind is AgentEventKind.USAGE:
        parts.append((kind, usage_payload(payload)))
    else:
        parts.append((kind, {}))
    usage = usage_payload(payload)
    if usage and all(part[0] is not AgentEventKind.USAGE for part in parts):
        parts.append((AgentEventKind.USAGE, usage))
    return parts


def _codex_tool_payload(
    payload: dict[str, object],
    item: Mapping[str, object],
    item_type: str | None,
    kind: AgentEventKind,
) -> dict[str, object]:
    canonical: dict[str, object] = {}
    call_id = first_string(item, "tool_call_id", "call_id", "id") or first_string(
        payload, "tool_call_id", "call_id", "id"
    )
    name = first_string(item, "tool_name", "name", "tool")
    if item_type == "command_execution":
        name = name or "shell"
        canonical["tool_type"] = "command"
    elif item_type == "mcp_tool_call":
        canonical["tool_type"] = "mcp"
    elif item_type:
        canonical["tool_type"] = "function"
    if call_id is not None:
        canonical["tool_call_id"] = call_id
    if name is not None:
        canonical["tool_name"] = name
    arguments = first_value(item, "arguments", "input", "args")
    command = first_value(item, "command")
    if arguments is not None:
        canonical["arguments"] = structured_value(arguments)
    elif command is not None:
        canonical["arguments"] = {"command": command}
    if kind is AgentEventKind.TOOL_RESULT:
        result = first_value(item, "result", "output", "aggregated_output")
        if result is not None:
            canonical["result"] = structured_value(result)
        exit_code = item.get("exit_code")
        is_error = bool(item.get("error")) or (
            isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
        )
        canonical["is_error"] = is_error
        canonical["status"] = "failed" if is_error else "succeeded"
    return canonical


def _event_kind(native_type: str, payload: dict[str, object]) -> AgentEventKind:
    lowered = native_type.lower()
    if "error" in lowered or lowered.endswith("failed"):
        return AgentEventKind.ERROR
    if "usage" in lowered:
        return AgentEventKind.USAGE
    if lowered.startswith("thread") or lowered.startswith("session"):
        return AgentEventKind.SESSION
    if "completed" in lowered and ("turn" in lowered or lowered == "completed"):
        return AgentEventKind.COMPLETED
    item = payload.get("item")
    item_type = str(item.get("type", "")) if isinstance(item, dict) else ""
    if (
        "tool" in lowered
        or "command" in lowered
        or item_type
        in {
            "command_execution",
            "mcp_tool_call",
        }
    ):
        return AgentEventKind.TOOL_RESULT if "completed" in lowered else AgentEventKind.TOOL_CALL
    if "message" in lowered or item_type in {"agent_message", "reasoning"}:
        return AgentEventKind.MESSAGE
    return AgentEventKind.UNKNOWN
