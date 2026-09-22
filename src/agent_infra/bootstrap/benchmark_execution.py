"""BM01 composition; existing research Controller and Docker services are untouched."""

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_infra.benchmarks.api import CapabilityProfile
from agent_infra.benchmarks.execution import (
    execution_spec,
    prepare_execution,
    read_execution,
    validate_backend,
    write_execution,
)
from agent_infra.benchmarks.planning import check_plan, read_plan
from agent_infra.benchmarks.registry import AdapterRegistry
from agent_infra.bootstrap.paths import state_root
from agent_infra.environments.managed_process import ManagedProcessBackend
from agent_infra.records.api import EventQuery
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.benchmark_execution import BenchmarkExecutionService
from agent_infra.runs.control_store import RunControlStore


def execution_action(args: argparse.Namespace, registry: AdapterRegistry) -> dict[str, Any]:
    action = args.benchmark_command
    if action == "prepare":
        frozen = read_plan(args.plan)
        if args.output.resolve().is_relative_to(Path(frozen.source.path).resolve()):
            raise ValueError("execution output must be outside the immutable source")
        execution = prepare_execution(frozen, registry.load_identity(frozen.adapter))
        # Validate the same spec schema that the backend will consume, before presenting it.
        execution_spec(execution, "preview-run", "preview-attempt", Path("/preview-workspace"))
        write_execution(execution, args.output)
        return {
            "output": str(args.output),
            "digest": execution.digest,
            "invocation": execution.invocation.model_dump(mode="json"),
            "runtime_ready": False,
            "next": "review command; run requires --allow-host-process",
        }
    prepared = None
    if action == "run":
        if not args.allow_host_process:
            raise ValueError(
                "review the prepared command and pass --allow-host-process to execute it"
            )
        prepared = read_execution(args.execution)
        loaded = registry.load_identity(prepared.frozen_plan.adapter)
        # All source and invocation checks happen before creating state or starting a process.
        if prepare_execution(prepared.frozen_plan, loaded) != prepared:
            raise ValueError("adapter invocation changed since execution was prepared")
        profile = CapabilityProfile.model_validate_json(args.capabilities.read_bytes())
        issues = check_plan(prepared.frozen_plan, loaded, profile)
        errors = [issue.message for issue in issues if issue.severity == "error"]
        if errors:
            raise ValueError("incompatible declarations: " + "; ".join(errors))
        validate_backend(prepared, ManagedProcessBackend.backend_id, ManagedProcessBackend.features)
    root = state_root(args.state_dir) / "benchmarks"
    store = RunControlStore(root)
    records = LocalRecordsStore(root / "records")
    backend = ManagedProcessBackend(root / "native")
    service = BenchmarkExecutionService(store, records, backend, root / "workspaces")
    if action == "run":
        assert prepared is not None
        run = service.submit(args.operation_id, prepared)
        return {key: value for key, value in run.items() if key != "request"}
    if action == "reconcile":
        return {
            "runs": [
                {key: value for key, value in run.items() if key != "request"}
                for run in service.reconcile()
            ]
        }
    run = service.status(args.run_id, cancel=action == "cancel")
    if action == "events":
        page = records.read_events(EventQuery(run_id=args.run_id, limit=200), args.cursor)
        return {"items": [asdict(item) for item in page.items], "next_cursor": page.next_cursor}
    if action == "artifacts":
        return {"items": [asdict(item) for item in records.list_artifacts(run["attempt_id"])]}
    # Do not print the administrative frozen plan or complete command on every status poll.
    return {key: value for key, value in run.items() if key != "request"}
