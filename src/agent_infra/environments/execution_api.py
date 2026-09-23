"""Durable execution contracts. No benchmark, scheduler or database implementation imports."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_infra.contracts.files import relative_path
from agent_infra.environments.api import CleanupResult, ProcessCommand, Submission


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False, hide_input_in_errors=True
    )

    run_id: str
    attempt_id: str
    unit_id: str
    phase_id: str
    command: ProcessCommand
    workspace: str
    outputs: tuple[str, ...] = ()
    cancellation_grace_seconds: float = Field(
        default=0.25, ge=0.25, le=120, exclude_if=lambda value: value == 0.25
    )
    max_log_bytes: Annotated[int, Field(gt=0, le=64 * 1024**2)] = 8 * 1024**2
    max_artifact_bytes: Annotated[int, Field(gt=0, le=1024**4)] = 16 * 1024**2

    @model_validator(mode="after")
    def valid(self) -> Self:
        for name in ("run_id", "attempt_id", "unit_id", "phase_id"):
            value = getattr(self, name)
            if not value or len(value) > 200 or "\0" in value:
                raise ValueError(f"invalid {name}")
        if not Path(self.workspace).is_absolute():
            raise ValueError("workspace must be absolute")
        command = self.command
        if (
            not 1 <= len(command.argv) <= 128
            or not command.argv[0]
            or any("\0" in arg for arg in command.argv)
            or sum(map(len, command.argv)) > 65536
        ):
            raise ValueError("command requires 1–128 arguments, no NUL, at most 64 KiB")
        if not math.isfinite(command.timeout_seconds) or not 0 < command.timeout_seconds <= 604800:
            raise ValueError("timeout must be finite and within 0–604800 seconds")
        if command.stdin_text is not None:
            raise ValueError("managed process stdin is disabled; use explicit input files")
        if command.environment:
            raise ValueError("environment/credential injection is not supported by this backend")
        if command.cwd != ".":
            relative_path(command.cwd)
        for output in self.outputs:
            relative_path(output)
        if len(set(self.outputs)) != len(self.outputs):
            raise ValueError("output paths must be unique")
        return self

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.model_dump_json().encode()).hexdigest()


@dataclass(frozen=True)
class ExecutionHandle:
    operation_id: str
    backend: str
    native_id: str | None
    spec_digest: str


@dataclass(frozen=True)
class Reconciliation:
    state: Literal["not_submitted", "known", "unknown"]
    handle: ExecutionHandle | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ExecutionObservation:
    status: str
    exit_code: int | None
    data: bytes
    next_cursor: int
    eof: bool
    logs_truncated: bool
    cleanup: CleanupResult
    usage: ResourceUsage | None = None
    allocation: ResourceAllocation | None = None


@dataclass(frozen=True)
class ResourceUsage:
    """Measured task usage; absent fields were not observed by this backend."""

    elapsed_seconds: float
    cpu_seconds: float | None = None
    memory_peak_bytes: int | None = None
    read_bytes: int | None = None
    write_bytes: int | None = None
    gpu_memory_peak_bytes: int | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class ResourceAllocation:
    """Physical limits observed by a backend, distinct from the scheduler lease."""

    cpu_cores: float | None
    memory_bytes: int | None
    gpu_count: int | None
    source: str


class ExecutionBackend(Protocol):
    backend_id: str
    features: tuple[str, ...]
    cleanup_scope: str

    def submit(self, operation_id: str, spec: ExecutionSpec) -> ExecutionHandle: ...
    def reconcile(self, operation_id: str) -> Reconciliation: ...
    def observe(self, handle: ExecutionHandle, cursor: int = 0) -> ExecutionObservation: ...
    def cancel(self, handle: ExecutionHandle) -> CleanupResult: ...
    def cleanup(self, handle: ExecutionHandle) -> CleanupResult: ...
    def collect(self, handle: ExecutionHandle) -> Submission: ...
