"""Optional SDK execution extension 1.0; planning-only packages remain valid."""

from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from agent_infra.benchmarks.api import Contract, ExecutionPlan
from agent_infra.environments.api import ProcessCommand
from agent_infra.environments.execution_api import ExecutionBackend


class NativeInvocation(Contract):
    command: ProcessCommand
    outputs: tuple[str, ...] = ()
    cancellation_grace_seconds: float = Field(
        default=0.25, ge=0.25, le=120, exclude_if=lambda value: value == 0.25
    )
    max_log_bytes: int = Field(
        default=8 * 1024**2,
        gt=0,
        le=64 * 1024**2,
        exclude_if=lambda value: value == 8 * 1024**2,
    )
    max_artifact_bytes: int = Field(
        default=16 * 1024**2,
        gt=0,
        le=1024**4,
        exclude_if=lambda value: value == 16 * 1024**2,
    )


class BenchmarkExecutionAdapter(Protocol):
    """Pure translation. Do not execute anything in this method."""

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation: ...


class NativeRuntimeAdapter(Protocol):
    """Optional trusted runtime extension. Loaded only via the pinned adapter allowlist.

    The factory must not launch work. Validation must reject unsupported resources,
    visibility and clocks before submission. Interpretation consumes collected evidence.
    """

    def execution_backend(self, root: Path) -> ExecutionBackend: ...
    def validate_execution(self, plan: ExecutionPlan, invocation: NativeInvocation) -> None: ...
    def interpret(self, root: Path) -> dict[str, Any]: ...
