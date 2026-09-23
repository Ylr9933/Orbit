"""Compose explicitly enabled benchmark runtimes; research Controller is independent."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from agent_infra.benchmarks.api import CapabilityProfile
from agent_infra.benchmarks.execution import (
    PreparedExecution,
    execution_spec,
    prepare_execution,
    read_execution,
    validate_backend,
    write_execution,
)
from agent_infra.benchmarks.execution_api import NativeRuntimeAdapter
from agent_infra.benchmarks.planning import check_plan, read_plan
from agent_infra.benchmarks.registry import AdapterRegistry
from agent_infra.bootstrap.paths import state_root
from agent_infra.environments.execution_api import ExecutionBackend
from agent_infra.environments.managed_process import ManagedProcessBackend
from agent_infra.records.api import EventQuery
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources.persistent import PersistentLeaseStore
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
            "next": "review resources; use --allow-host-process or --allow-native-runtime",
        }
    prepared = None
    if action == "run":
        if not args.allow_host_process and not getattr(args, "allow_native_runtime", False):
            raise ValueError(
                "review execution and pass --allow-host-process or --allow-native-runtime"
            )
        prepared = read_execution(args.execution)
        is_host = prepared.frozen_plan.plan.phases[0].backend == ManagedProcessBackend.backend_id
        if is_host and not args.allow_host_process:
            raise ValueError("host execution requires --allow-host-process")
        if not is_host and not getattr(args, "allow_native_runtime", False):
            raise ValueError("native execution requires --allow-native-runtime")
        loaded = registry.load_identity(prepared.frozen_plan.adapter)
        # All source and invocation checks happen before creating state or starting a process.
        if prepare_execution(prepared.frozen_plan, loaded) != prepared:
            raise ValueError("adapter invocation changed since execution was prepared")
        profile = CapabilityProfile.model_validate_json(args.capabilities.read_bytes())
        issues = check_plan(prepared.frozen_plan, loaded, profile)
        errors = [issue.message for issue in issues if issue.severity == "error"]
        if errors:
            raise ValueError("incompatible declarations: " + "; ".join(errors))
    root = state_root(args.state_dir) / "benchmarks"
    store = RunControlStore(root)
    records = LocalRecordsStore(root / "records")
    leases = PersistentLeaseStore(root / "leases")

    if action == "queue":

        def lease_document(value: Any) -> dict[str, Any]:
            document = asdict(value)
            document["state"] = value.state.value
            document["created_at"] = value.created_at.isoformat()
            document["updated_at"] = value.updated_at.isoformat()
            return document

        return {
            "queued": [
                {key: value for key, value in item.items() if key != "request"}
                for item in store.queued()
            ],
            "leases": [lease_document(item) for item in leases.list()],
        }

    def service_for(execution: PreparedExecution) -> BenchmarkExecutionService:
        backend: ExecutionBackend
        if execution.frozen_plan.plan.phases[0].backend == ManagedProcessBackend.backend_id:
            if action == "run" and not args.allow_host_process:
                raise ValueError("review the command and pass --allow-host-process")
            backend = ManagedProcessBackend(root / "native")
            validate_backend(execution, backend.backend_id, backend.features)
            return BenchmarkExecutionService(
                store, records, backend, root / "workspaces", leases=leases
            )
        if action == "run" and not args.allow_native_runtime:
            raise ValueError("review native containers/resources and pass --allow-native-runtime")
        runtime = cast(
            NativeRuntimeAdapter,
            registry.load_identity(execution.frozen_plan.adapter).implementation,
        )
        if not all(
            callable(getattr(runtime, name, None))
            for name in ("execution_backend", "validate_execution", "interpret")
        ):
            raise ValueError("adapter does not provide the native runtime extension")
        backend = runtime.execution_backend(root / "native")

        def validate(value: PreparedExecution) -> None:
            runtime.validate_execution(value.frozen_plan.plan, value.invocation)

        return BenchmarkExecutionService(
            store,
            records,
            backend,
            root / "workspaces",
            validate_native=validate,
            interpret=runtime.interpret,
            leases=leases,
        )

    def existing(run: dict[str, Any]) -> BenchmarkExecutionService:
        return service_for(
            PreparedExecution.model_validate_json(json.dumps(run["request"]["execution"]))
        )

    if action == "run":
        assert prepared is not None
        run = service_for(prepared).submit(args.operation_id, prepared)
        return {key: value for key, value in run.items() if key != "request"}
    if action == "reconcile":
        return {
            "runs": [
                {key: value for key, value in run.items() if key != "request"}
                for pending in store.unfinished()
                for run in [existing(pending).status(pending["run_id"])]
            ]
        }
    run = existing(store.get(args.run_id)).status(args.run_id, cancel=action == "cancel")
    if action == "events":
        page = records.read_events(EventQuery(run_id=args.run_id, limit=200), args.cursor)
        return {"items": [asdict(item) for item in page.items], "next_cursor": page.next_cursor}
    if action == "artifacts":
        return {"items": [asdict(item) for item in records.list_artifacts(run["attempt_id"])]}
    # Do not print the administrative frozen plan or complete command on every status poll.
    return {key: value for key, value in run.items() if key != "request"}
