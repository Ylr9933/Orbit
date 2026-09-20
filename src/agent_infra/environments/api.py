"""Runtime-neutral process and isolation contracts consumed by Run."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InputMount:
    source: Path
    target: str


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Solver/evaluation are readonly; build is a credential-free template-only phase."""

    key: str
    phase: str
    image: str
    workspace: Path
    cpu_cores: float
    memory_bytes: int
    gpu_device_ids: tuple[str, ...] = ()
    readonly_inputs: tuple[InputMount, ...] = ()
    private_home: Path | None = None
    home_target: str = "/home/agent"
    network: bool = False


@dataclass(frozen=True, slots=True)
class ProcessCommand:
    argv: tuple[str, ...]
    cwd: str = "/workspace"
    stdin_text: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    timeout_seconds: float = 60


@dataclass(frozen=True, slots=True)
class EnvironmentHandle:
    id: str


@dataclass(frozen=True, slots=True)
class LogCursor:
    stdout: int = 0
    stderr: int = 0


@dataclass(frozen=True, slots=True)
class Observation:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    cursor: LogCursor
    logs_truncated: bool = False


@dataclass(frozen=True, slots=True)
class CleanupResult:
    complete: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Submission:
    root: Path
    digest: str
    files: tuple[str, ...]
    missing: tuple[str, ...]


class Environment(Protocol):
    def prepare(self, spec: SandboxSpec) -> EnvironmentHandle: ...
    def start(self, handle: EnvironmentHandle, command: ProcessCommand) -> None: ...
    def observe(
        self, handle: EnvironmentHandle, cursor: LogCursor | None = None
    ) -> Observation: ...
    def cancel(self, handle: EnvironmentHandle) -> CleanupResult: ...
    def cleanup(self, handle: EnvironmentHandle) -> CleanupResult: ...
    def collect(
        self, handle: EnvironmentHandle, paths: tuple[str, ...], destination: Path
    ) -> Submission: ...
