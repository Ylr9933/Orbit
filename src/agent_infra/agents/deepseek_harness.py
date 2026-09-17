"""DeepSeek Harness headless adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import replace
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
    AgentPlacement,
    AgentProbe,
    AgentRunRequest,
    BindMount,
)

DSH_PROVIDER = "dsh"
DSH_VERSION = "0.1.6-alpha.1"
DSH_NPM_PACKAGE = f"@deepseek-ai/dsh@{DSH_VERSION}"
DEFAULT_DSH_IMAGE = f"agent-infra/deepseek-harness:{DSH_VERSION}"
CONTAINER_DSH_HOME = "/home/agent/.dsh"
CONTAINER_WORKSPACE = "/workspace"


class DeepSeekHarnessAdapter:
    """Translate common requests into one-shot DSH headless plans."""

    def __init__(
        self,
        *,
        binary: str = "dsh",
        container_image: str = DEFAULT_DSH_IMAGE,
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
            provider=DSH_PROVIDER,
            display_name="DeepSeek Harness",
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
    def host_dsh_home(self) -> Path:
        configured = self._environ.get("DSH_HOME")
        if configured:
            return Path(configured).expanduser()
        configured_home = self._environ.get("HOME")
        return (Path(configured_home) if configured_home else Path.home()) / ".dsh"

    @property
    def host_settings_file(self) -> Path | None:
        for filename in ("settings.yaml", "settings.yml", "settings.json"):
            candidate = self.host_dsh_home / filename
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        return None

    @property
    def host_credentials_file(self) -> Path | None:
        candidate = self.host_dsh_home / ".credentials.yaml"
        return candidate if candidate.is_file() and not candidate.is_symlink() else None

    def probe(self) -> AgentProbe:
        probe = probe_npm_cli(
            provider=DSH_PROVIDER,
            binary=self._binary,
            npm_package=DSH_NPM_PACKAGE,
            runner=self._runner,
            auth_args=None,
            container_config_reusable=(
                self.host_settings_file is not None and self.host_credentials_file is not None
            ),
        )
        if probe.available and probe.version != DSH_VERSION:
            return replace(
                probe,
                compatible=False,
                issues=(
                    *probe.issues,
                    f"DSH {DSH_VERSION} is required for JSON events and session resume.",
                ),
            )
        return probe

    def ensure_installed(self) -> AgentProbe:
        return ensure_npm_cli(
            self.probe,
            self._runner,
            install_spec=DSH_NPM_PACKAGE,
            expected_version=DSH_VERSION,
        )

    def stage_container_credentials(self, destination: Path) -> Path:
        settings = self.host_settings_file
        if settings is None:
            raise FileNotFoundError("DSH settings are unavailable; configure a model first")
        credentials = self.host_credentials_file
        if credentials is None:
            raise FileNotFoundError(
                "DSH file credentials are unavailable; environment-only secrets require "
                "Environment secret injection"
            )
        return stage_private_files(
            source_home=settings.parent,
            destination=destination,
            filenames=(settings.name, credentials.name),
        )

    def create_launch_plan(
        self, request: AgentRunRequest, *, credential_home: Path | None = None
    ) -> AgentLaunchPlan:
        if not request.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not request.prompt.strip():
            raise ValueError("prompt must not be empty")
        if request.model is not None or request.reasoning_effort is not None:
            raise ValueError("DSH selects its model and reasoning policy from the active profile")

        runtime_workspace = (
            CONTAINER_WORKSPACE
            if request.placement is AgentPlacement.CONTAINER
            else str(request.workspace.resolve())
        )
        binary = "dsh" if request.placement is AgentPlacement.CONTAINER else self._binary
        argv = [binary, "--profile", "headless", "--json"]
        if request.resume_session_id:
            argv.extend(["--session-id", request.resume_session_id])

        mounts: tuple[BindMount, ...] = ()
        environment: tuple[tuple[str, str], ...] = ()
        image: str | None = None
        if request.placement is AgentPlacement.CONTAINER:
            if credential_home is None:
                raise ValueError("container placement requires an isolated credential_home")
            environment = (("HOME", "/home/agent"), ("DSH_HOME", CONTAINER_DSH_HOME))
            mounts = (
                BindMount(credential_home.resolve(), CONTAINER_DSH_HOME, read_only=False),
                BindMount(request.workspace.resolve(), CONTAINER_WORKSPACE, read_only=False),
            )
            image = self._container_image

        return AgentLaunchPlan(
            provider=DSH_PROVIDER,
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
            parts = _dsh_event_parts(native_type, payload)
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


def _dsh_event_parts(
    native_type: str, payload: dict[str, object]
) -> list[tuple[AgentEventKind, dict[str, object]]]:
    kind = _dsh_event_kind(native_type, payload)
    canonical: dict[str, object] = {}
    if kind is AgentEventKind.SESSION:
        session_id = first_string(payload, "session_id", "id")
        if session_id is not None:
            canonical["session_id"] = session_id
    elif kind is AgentEventKind.MESSAGE:
        canonical["role"] = "assistant"
        text = text_value(first_value(payload, "text", "content", "message", "thinking"))
        if text is not None:
            canonical["text"] = text
    elif kind in {AgentEventKind.TOOL_CALL, AgentEventKind.TOOL_RESULT}:
        function = as_mapping(payload.get("function"))
        call_id = first_string(payload, "tool_call_id", "call_id", "id")
        name = first_string(payload, "tool_name", "name") or first_string(function, "name")
        if call_id is not None:
            canonical["tool_call_id"] = call_id
        if name is not None:
            canonical["tool_name"] = name
        canonical["tool_type"] = "function"
        if kind is AgentEventKind.TOOL_CALL:
            arguments = first_value(payload, "arguments", "args", "input")
            if arguments is None:
                arguments = first_value(function, "arguments", "args")
            if arguments is not None:
                canonical["arguments"] = structured_value(arguments)
        else:
            result = first_value(payload, "result", "output", "content")
            if result is not None:
                canonical["result"] = structured_value(result)
            is_error = payload.get("is_error") is True or payload.get("error") is not None
            canonical["is_error"] = is_error
            canonical["status"] = "failed" if is_error else "succeeded"
    elif kind is AgentEventKind.USAGE:
        canonical.update(usage_payload(payload))
    elif kind is AgentEventKind.COMPLETED:
        session_id = first_string(payload, "session_id")
        finish_reason = first_string(payload, "finish_reason", "status")
        if session_id is not None:
            canonical["session_id"] = session_id
        if finish_reason is not None:
            canonical["finish_reason"] = finish_reason
    elif kind is AgentEventKind.ERROR:
        canonical.update(error_payload(payload))
    return [(kind, canonical)]


def _dsh_event_kind(native_type: str, payload: dict[str, object]) -> AgentEventKind:
    if native_type == "session":
        return AgentEventKind.SESSION
    if native_type in {"text", "thinking"}:
        return AgentEventKind.MESSAGE
    if native_type == "tool_call":
        return AgentEventKind.TOOL_CALL
    if native_type == "tool_result":
        return AgentEventKind.TOOL_RESULT
    if native_type == "error":
        return AgentEventKind.ERROR
    if native_type == "final":
        return AgentEventKind.COMPLETED
    if native_type == "status" and "usage" in payload:
        return AgentEventKind.USAGE
    return AgentEventKind.UNKNOWN
