"""Freeze an optional adapter invocation separately from stable BM00 planning files."""

import json
import os
from pathlib import Path
from typing import cast

from agent_infra.benchmarks.api import Contract, Digest
from agent_infra.benchmarks.execution_api import BenchmarkExecutionAdapter, NativeInvocation
from agent_infra.benchmarks.planning import FrozenPlan, adapter_call, canonical_digest, freeze_plan
from agent_infra.benchmarks.registry import AdapterError, LoadedAdapter
from agent_infra.contracts.files import content_digest
from agent_infra.environments.execution_api import ExecutionSpec


class PreparedExecution(Contract):
    schema_version: int = 1
    extension_version: str = "1.0"
    frozen_plan: FrozenPlan
    invocation: NativeInvocation
    digest: Digest


def prepare_execution(frozen: FrozenPlan, loaded: LoadedAdapter) -> PreparedExecution:
    current = freeze_plan(loaded, Path(frozen.source.path), frozen.plan.request)
    if current != frozen:
        raise AdapterError(
            "plan/source/adapter changed; regenerate the plan before preparing execution"
        )
    if not callable(getattr(loaded.implementation, "invocation", None)):
        raise AdapterError("adapter supports planning only; execution extension 1.0 is required")
    if len(frozen.plan.units) != 1 or len(frozen.plan.phases) != 1:
        raise AdapterError("BM01 executes one atomic unit and one native-owned phase")
    phase = frozen.plan.phases[0]
    if phase.owner != "native":
        raise AdapterError(
            "BM01 requires a native-owned phase; platform phase scheduling is pending"
        )
    adapter = cast(BenchmarkExecutionAdapter, loaded.implementation)
    invocation = adapter_call(
        "invocation", lambda: adapter.invocation(frozen.plan), NativeInvocation
    )
    if content_digest(Path(frozen.source.path)) != frozen.source.digest:
        raise AdapterError("source changed while preparing invocation")
    body = {
        "schema_version": 1,
        "extension_version": "1.0",
        "frozen_plan": frozen.model_dump(mode="json"),
        "invocation": invocation.model_dump(mode="json"),
    }
    return PreparedExecution.model_validate_json(
        json.dumps({**body, "digest": canonical_digest(body)})
    )


def read_execution(path: Path) -> PreparedExecution:
    execution = PreparedExecution.model_validate_json(path.read_bytes())
    if execution.schema_version != 1 or execution.extension_version != "1.0":
        raise AdapterError("unsupported prepared execution schema/extension")
    if canonical_digest(execution.model_dump(mode="json", exclude={"digest"})) != execution.digest:
        raise AdapterError("prepared execution digest mismatch")
    return execution


def write_execution(execution: PreparedExecution, path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(execution.model_dump_json(indent=2) + "\n")


def execution_spec(
    execution: PreparedExecution, run_id: str, attempt_id: str, workspace: Path
) -> ExecutionSpec:
    plan = execution.frozen_plan.plan
    return ExecutionSpec(
        run_id=run_id,
        attempt_id=attempt_id,
        unit_id=plan.units[0].unit_id,
        phase_id=plan.phases[0].phase_id,
        command=execution.invocation.command,
        workspace=str(workspace.absolute()),
        outputs=execution.invocation.outputs,
        cancellation_grace_seconds=execution.invocation.cancellation_grace_seconds,
        max_log_bytes=execution.invocation.max_log_bytes,
        max_artifact_bytes=execution.invocation.max_artifact_bytes,
    )


def validate_backend(
    execution: PreparedExecution,
    backend_id: str,
    features: tuple[str, ...],
    *,
    native_runtime: bool = False,
) -> None:
    plan = execution.frozen_plan.plan
    if len(plan.units) != 1 or len(plan.phases) != 1 or plan.phases[0].owner != "native":
        raise ValueError("BM01 requires one atomic unit and one native-owned phase")
    phase = plan.phases[0]
    if plan.retry.owner == "platform":
        raise ValueError("BM01 does not implement platform-owned benchmark retries")
    if phase.backend != backend_id or set(phase.required_capabilities) - set(features):
        raise ValueError("actual backend cannot provide the plan's required execution capabilities")
    if native_runtime:
        return  # The explicitly enabled native extension validates its full request separately.
    resources = phase.resources.model_dump(exclude_none=True)
    if resources != {"allocator": "unspecified"}:
        raise ValueError(
            "host processes cannot enforce task allocations; use an allocation backend"
        )
    if any("solver" not in material.readers for material in phase.materials):
        raise ValueError("managed host processes cannot isolate private task materials")
    budget = phase.budget
    if budget.wall_seconds is not None and (
        budget.clock != "process_start"
        or execution.invocation.command.timeout_seconds != budget.wall_seconds
    ):
        raise ValueError(
            "native budget/clock needs backend support; it cannot be replaced by a host timeout"
        )
