"""Single-attempt execution inputs and outcomes."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunRequest:
    task_manifest: Path
    resource_file: Path
    solver_image: str
    timeout_seconds: float = 60
    network: bool = False
    credential_home: Path | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    attempt_id: str
    status: str
    evaluation_status: str
    feedback_json: str
    submission_root: Path | None
    submission_digest: str | None
    cleanup_complete: bool
    lease_released: bool
    lease_id: str | None
    error: str | None = None
