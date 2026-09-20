"""Long-lived environment operations; Jobs are commands, not independent experiments."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agent_infra.environments.api import CleanupResult, EnvironmentHandle, SandboxSpec, Submission


@dataclass(frozen=True, slots=True)
class JobSpec:
    job_id: str
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: float = 3600


class ResearchEnvironment(Protocol):
    def prepare(self, spec: SandboxSpec) -> EnvironmentHandle: ...
    def start_job(self, handle: EnvironmentHandle, spec: JobSpec) -> dict[str, Any]: ...
    def job(
        self, handle: EnvironmentHandle, job_id: str, *, stop: bool = False
    ) -> dict[str, Any]: ...
    def logs(self, handle: EnvironmentHandle, job_id: str, cursor: int) -> dict[str, Any]: ...
    def file(
        self, handle: EnvironmentHandle, operation: str, path: str, **options: Any
    ) -> dict[str, Any]: ...
    def cleanup(self, handle: EnvironmentHandle) -> CleanupResult: ...
    def collect(self, handle: EnvironmentHandle, destination: Path) -> Submission: ...
