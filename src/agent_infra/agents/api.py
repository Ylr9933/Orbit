"""Provider-neutral contracts exposed by the Agent module."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class AgentPlacement(StrEnum):
    """Where an Agent process is expected to run."""

    HOST = "host"
    CONTAINER = "container"


class AgentPermissionMode(StrEnum):
    """How the Agent's command sandbox relates to the outer runtime."""

    WORKSPACE_WRITE = "workspace_write"
    OUTER_SANDBOX = "outer_sandbox"


class AgentCapability(StrEnum):
    """Capabilities that Run can use for compatibility checks."""

    INTERACTIVE = "interactive"
    NON_INTERACTIVE = "non_interactive"
    RESUME = "resume"
    EVENT_STREAM = "event_stream"
    HOST_EXECUTION = "host_execution"
    CONTAINER_EXECUTION = "container_execution"


class AgentEventKind(StrEnum):
    """Small normalized event vocabulary; native payloads remain available."""

    SESSION = "session"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    COMPLETED = "completed"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    provider: str
    display_name: str
    integration: str
    capabilities: frozenset[AgentCapability]


@dataclass(frozen=True, slots=True)
class AgentProbe:
    provider: str
    available: bool
    executable: str | None
    version: str | None
    authenticated: bool | None
    container_auth_reusable: bool
    compatible: bool = True
    issues: tuple[str, ...] = ()
    install_command: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: str
    prompt: str
    workspace: Path
    placement: AgentPlacement
    permission_mode: AgentPermissionMode = AgentPermissionMode.WORKSPACE_WRITE
    model: str | None = None
    reasoning_effort: str | None = None
    resume_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class BindMount:
    """A mount requirement consumed by a container Environment backend."""

    source: Path
    target: str
    read_only: bool


@dataclass(frozen=True, slots=True)
class AgentLaunchPlan:
    """A shell-free process plan; Environment owns its execution lifecycle."""

    provider: str
    placement: AgentPlacement
    argv: tuple[str, ...]
    cwd: str
    stdin_text: str | None
    environment: tuple[tuple[str, str], ...] = ()
    mounts: tuple[BindMount, ...] = ()
    container_image: str | None = None

    def environment_dict(self) -> dict[str, str]:
        return dict(self.environment)


@dataclass(frozen=True, slots=True)
class AgentEvent:
    sequence: int
    kind: AgentEventKind
    native_type: str
    payload: Mapping[str, object]


class AgentAdapter(Protocol):
    """Common discovery contract for CLI and in-process Agent integrations."""

    @property
    def descriptor(self) -> AgentDescriptor: ...

    def probe(self) -> AgentProbe: ...


class CommandAgentAdapter(AgentAdapter, Protocol):
    """Additional contract for Agents launched as an external command."""

    def create_launch_plan(
        self, request: AgentRunRequest, *, credential_home: Path | None = None
    ) -> AgentLaunchPlan: ...

    def decode_events(self, lines: Iterator[str]) -> Iterator[AgentEvent]: ...


class InstallableCommandAgentAdapter(CommandAgentAdapter, Protocol):
    """Command Agent that can install its CLI when it is absent."""

    def ensure_installed(self) -> AgentProbe: ...

    def stage_container_credentials(self, destination: Path) -> Path: ...
