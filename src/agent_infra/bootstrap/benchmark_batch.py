"""Batch composition over the existing single-run lifecycle and persistent queue."""

import argparse
import fcntl
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_infra.benchmarks.api import CapabilityProfile, PlanRequest
from agent_infra.benchmarks.batch import BatchPlan, summarize
from agent_infra.benchmarks.execution import prepare_execution, read_execution, write_execution
from agent_infra.benchmarks.planning import canonical_digest, check_plan, freeze_plan
from agent_infra.benchmarks.registry import AdapterRegistry, load_config
from agent_infra.bootstrap.benchmark_execution import _validate_submission, execution_action
from agent_infra.resources.api import LeaseCapacity
from agent_infra.resources.persistent import PersistentLeaseStore
from agent_infra.runs.control_store import RunControlStore


def _write(path: Path, data: object) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not args.declare_compatibility:
        raise ValueError("review native/model requirements and pass --declare-compatibility")
    if not 1 <= args.concurrency <= 64:
        raise ValueError("concurrency must be 1–64")
    sources = sorted(p for p in args.sources.glob(args.pattern) if p.is_dir())
    if not sources:
        raise ValueError("no matching instance directories")
    if any(root.is_relative_to(p.resolve()) for p in sources):
        raise ValueError("batch output must be outside source instances")
    if root.exists():
        raise ValueError("batch directory already exists; use submit/status to resume it")
    registry = AdapterRegistry(load_config(args.config))
    loaded = registry.load(args.adapter)
    template = json.loads(args.request.read_text())
    executions = []
    combinations = []
    features: dict[str, set[str]] = {}
    for source in sources:
        catalog = loaded.implementation.discover(source)
        if len(catalog.units) != 1:
            raise ValueError("batch preparation requires one atomic unit per source")
        body = {**template, "selection": [catalog.units[0].unit_id]}
        request = PlanRequest.model_validate_json(json.dumps(body))
        frozen = freeze_plan(loaded, source, request)
        execution = prepare_execution(frozen, loaded)
        executions.append(execution)
        phase = frozen.plan.phases[0]
        features.setdefault(phase.backend, set()).update(phase.required_capabilities)
        combinations.append(
            dict(
                adapter_id=loaded.identity.adapter_id,
                adapter_version=loaded.identity.version,
                suite_digest=frozen.plan.suite.source.digest,
                runner_digest=frozen.plan.suite.runner.digest,
                profile=frozen.plan.suite.profile,
                agent=request.candidate.agent,
                agent_version=request.candidate.agent_version,
                model=request.candidate.model,
                backend=phase.backend,
            )
        )
    capabilities = CapabilityProfile.model_validate_json(
        json.dumps(
            dict(
                backends=[dict(backend=k, features=sorted(v)) for k, v in features.items()],
                agents=[executions[0].frozen_plan.plan.request.candidate.agent],
                combinations=combinations,
            )
        )
    )
    for execution in executions:
        errors = [
            i.message
            for i in check_plan(execution.frozen_plan, loaded, capabilities)
            if i.severity == "error"
        ]
        if errors:
            raise ValueError("incompatible batch member: " + "; ".join(errors))
    # Publish a batch manifest only after every source, model declaration and invocation validates.
    root.mkdir(parents=True, mode=0o700)
    (root / "executions").mkdir()
    (root / "adapters.toml").write_bytes(args.config.read_bytes())
    _write(root / "capabilities.json", capabilities.model_dump(mode="json"))
    members = []
    for index, execution in enumerate(executions):
        name = f"executions/{index:04d}.json"
        write_execution(execution, root / name)
        members.append(
            dict(
                operation_id="batch-" + execution.digest.removeprefix("sha256:"),
                execution=name,
                execution_digest=execution.digest,
                unit_id=execution.frozen_plan.plan.units[0].unit_id,
            )
        )
    body = dict(
        schema_version=1,
        members=members,
        concurrency=args.concurrency,
        model=executions[0].frozen_plan.plan.request.candidate.model,
        capability_scope="operator_declared_not_runtime_attested",
    )
    batch = BatchPlan.model_validate_json(json.dumps({**body, "digest": canonical_digest(body)}))
    _write(root / "batch.json", batch.model_dump(mode="json"))
    return dict(
        directory=str(root),
        total=len(members),
        concurrency=batch.concurrency,
        model=batch.model,
        runtime_ready=False,
        capability_scope=batch.capability_scope,
    )


def _context(root: Path) -> tuple[BatchPlan, AdapterRegistry, argparse.Namespace]:
    batch = BatchPlan.model_validate_json((root / "batch.json").read_bytes())
    registry = AdapterRegistry(load_config(root / "adapters.toml"))
    common = argparse.Namespace(
        config=root / "adapters.toml",
        state_dir=str(root / "state"),
        capabilities=root / "capabilities.json",
        allow_native_runtime=True,
        allow_host_process=False,
        budget_group="batch-" + batch.digest.removeprefix("sha256:"),
        budget_wall_seconds=None,
    )
    return batch, registry, common


def _summary(root: Path, batch: BatchPlan) -> dict[str, Any]:
    state = root / "state" / "benchmarks"
    runs = (
        RunControlStore(state, read_only=True).ordered()
        if (state / "control.sqlite3").exists()
        else []
    )
    result = summarize(batch, runs)
    if (root / "blocked.json").exists():
        result["blocked"] = json.loads((root / "blocked.json").read_text())
    _write(root / "summary.json", result)
    lines = [
        "# Benchmark batch",
        "",
        f"Model: `{batch.model}`; concurrency: {batch.concurrency}",
        "",
        f"Finished: {result['finished']}/{result['total']}; scored: {result['scored']}",
        "",
        f"Failed: {result['failed']}; cancelled: {result['cancelled']}",
        "",
        "Local results only; no official suite score.",
        "",
        "| Task | State | Execution | Evaluation | Metrics | Run |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if result.get("blocked"):
        lines[1:1] = ["", "**Stopped: " + result["blocked"]["reason"] + "**"]
    for row in result["runs"]:
        cells = [
            row[k] for k in ("unit_id", "state", "execution", "evaluation", "metrics", "run_id")
        ]
        lines.append(
            "| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in cells) + " |"
        )
    (root / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    return result


def _refresh_active(
    root: Path, batch: BatchPlan, registry: AdapterRegistry, common: argparse.Namespace
) -> dict[str, Any]:
    """Collect active outcomes before allowing a fresh queue admission."""
    snapshot = _summary(root, batch)
    for row in snapshot["runs"]:
        if row["state"] not in {"queued", "not_submitted", "finished"}:
            execution_action(
                argparse.Namespace(
                    **vars(common), benchmark_command="status", run_id=row["run_id"]
                ),
                registry,
            )
    snapshot = _summary(root, batch)
    failures = [
        row
        for row in snapshot["runs"]
        if row["failure_reason"] in {"model_unavailable", "model_authentication_failed"}
    ]
    if failures:
        _write(
            root / "blocked.json",
            {"reason": failures[0]["failure_reason"], "run_id": failures[0]["run_id"]},
        )
        for row in sorted(snapshot["runs"], key=lambda row: row["state"] != "queued"):
            if row["state"] not in {"not_submitted", "finished"}:
                execution_action(
                    argparse.Namespace(
                        **vars(common), benchmark_command="cancel", run_id=row["run_id"]
                    ),
                    registry,
                )
        return _summary(root, batch)
    return snapshot


def batch_action(args: argparse.Namespace) -> dict[str, Any]:
    root = args.directory.resolve()
    if args.batch_command == "prepare":
        return _prepare(args, root)
    batch, registry, common = _context(root)
    if args.batch_command == "submit":
        if (root / "blocked.json").exists():
            raise ValueError("batch stopped for a model error; resolve it and prepare a new batch")
        if not args.allow_native_runtime:
            raise ValueError("review the batch and pass --allow-native-runtime")
        with (root / ".submit.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            executions = []
            for member in batch.members:
                path = (root / member.execution).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("batch execution path escapes batch directory")
                execution = read_execution(path)
                if execution.digest != member.execution_digest:
                    raise ValueError("batch execution changed")
                _validate_submission(execution, common, registry)
                executions.append(execution)
            resources = [e.frozen_plan.plan.phases[0].resources for e in executions]
            if any(r.allocator != "local" for r in resources):
                raise ValueError("batch capacity currently supports local allocation only")
            capacity = LeaseCapacity(
                max_concurrent=batch.concurrency,
                cpu_cores=max(r.cpu_cores or 0 for r in resources) * batch.concurrency,
                memory_bytes=max(r.memory_bytes or 0 for r in resources) * batch.concurrency,
                gpu_count=max(r.gpu_count or 0 for r in resources) * batch.concurrency,
            )
            leases = PersistentLeaseStore(root / "state/benchmarks/leases")
            if leases.capacity != capacity:
                leases.configure(capacity)
            _write(root / "capacity.json", asdict(capacity))
            common.budget_wall_seconds = sum(
                e.frozen_plan.plan.phases[0].budget.wall_seconds or 0 for e in executions
            )
            if common.budget_wall_seconds <= 0:
                raise ValueError("batch members must declare finite wall budgets")
            for member in batch.members:
                if _refresh_active(root, batch, registry, common).get("blocked"):
                    return _summary(root, batch)
                command = argparse.Namespace(
                    **vars(common),
                    benchmark_command="run",
                    execution=root / member.execution,
                    operation_id=member.operation_id,
                )
                execution_action(command, registry)
                _summary(root, batch)
        return _summary(root, batch)
    if args.batch_command == "worker":
        # Existing reconcile owns launching, polling, collecting and lease release.
        command = argparse.Namespace(**vars(common), benchmark_command="reconcile")
        while True:
            if _refresh_active(root, batch, registry, common).get("blocked"):
                return _summary(root, batch)
            execution_action(command, registry)
            result = _summary(root, batch)
            if result["finished"] == result["total"]:
                return result
            time.sleep(5)
    return _summary(root, batch)
