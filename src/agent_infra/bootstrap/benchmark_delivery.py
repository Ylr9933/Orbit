"""Compose BM07 compatibility and native submission commands without starting a worker."""

import argparse
import os
import uuid
from pathlib import Path
from typing import Any, cast

from agent_infra.benchmarks.api import AdapterIdentity
from agent_infra.benchmarks.compatibility import CompatibilityEntry, read_matrix
from agent_infra.benchmarks.registry import AdapterRegistry
from agent_infra.benchmarks.submission_api import NativeSubmissionAdapter
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.benchmark_submission import BenchmarkSubmissionService
from agent_infra.runs.control_store import RunControlStore


def _handoff(args: argparse.Namespace, registry: AdapterRegistry, root: Path) -> dict[str, Any]:
    records = LocalRecordsStore(root / "records")
    handoff = BenchmarkSubmissionService(root / "submissions", records)
    if args.handoff_command == "status":
        return handoff.status(args.run_id)
    if args.config is None:
        raise ValueError("native handoff requires --config")
    if args.handoff_command == "prepare":
        run = RunControlStore(root, read_only=True).get(args.run_id)
        frozen = run["request"]["execution"]["frozen_plan"]
        identity = AdapterIdentity.model_validate(frozen["adapter"])
        adapter = cast(NativeSubmissionAdapter, registry.load_identity(identity).implementation)
        if not callable(getattr(adapter, "prepare_submission", None)):
            raise ValueError("adapter has no native submission handoff extension")
        return handoff.prepare(run, identity, adapter.prepare_submission)
    if not args.confirm_native_submit:
        raise ValueError("native submission requires --confirm-native-submit")
    current = handoff.status(args.run_id)
    identity = AdapterIdentity.model_validate(current["handoff"]["adapter"])
    adapter = cast(NativeSubmissionAdapter, registry.load_identity(identity).implementation)
    if not callable(getattr(adapter, "send_submission", None)):
        raise ValueError("adapter has no native submission sender")
    return handoff.send(args.run_id, adapter.send_submission)


def _check_run_evidence(entry: CompatibilityEntry, run: dict[str, Any]) -> None:
    frozen = run["request"]["execution"]["frozen_plan"]
    plan = frozen["plan"]
    candidate = plan["request"]["candidate"]
    if (
        frozen["adapter"]["adapter_id"] != entry.adapter_id
        or frozen["adapter"]["distribution"] != entry.distribution
        or frozen["adapter"]["version"] != entry.adapter_version
        or plan["suite"]["source"]["digest"] != entry.suite_digest
        or plan["suite"]["runner"]["digest"] != entry.runner_digest
        or plan["suite"]["profile"] != entry.profile
        or plan["phases"][0]["backend"] != entry.backend
        or candidate["agent"] != entry.agent
        or candidate["agent_version"] != entry.agent_version
        or candidate["model"] != entry.model
    ):
        raise ValueError(f"matrix run evidence differs from {entry.alias} tuple")
    result = run.get("result") or {}
    if entry.level in {"runnable", "scored", "protocol_validated"} and (
        run["state"] != "finished" or result.get("execution") != "completed"
    ):
        raise ValueError("runnable claim requires a completed local run")
    if entry.level in {"scored", "protocol_validated"} and result.get("evaluation") != "scored":
        raise ValueError("scored claim requires a scored local run")
    if entry.level == "protocol_validated" and result.get("protocol") != "valid":
        raise ValueError("validated claim requires a protocol-valid local run")


def _publish_matrix(
    args: argparse.Namespace, registry: AdapterRegistry, root: Path
) -> dict[str, Any]:
    if args.config is None:
        raise ValueError("publishing compatibility claims requires --config")
    if args.file.stat().st_size > 1024 * 1024:
        raise ValueError("compatibility matrix exceeds 1 MiB")
    matrix = read_matrix(args.file)
    checked_runs = 0
    store: RunControlStore | None = None
    for item in matrix.entries:
        loaded = registry.load(item.alias)
        identity = loaded.identity
        if (
            identity.adapter_id != item.adapter_id
            or identity.distribution != item.distribution
            or identity.version != item.adapter_version
        ):
            raise ValueError(f"matrix entry {item.alias} differs from enabled adapter identity")
        if item.official_submission == "native" and not all(
            callable(getattr(loaded.implementation, name, None))
            for name in ("prepare_submission", "send_submission")
        ):
            raise ValueError(f"matrix entry {item.alias} has no native submission extension")
        for reference in item.evidence:
            if not reference.startswith("run:"):
                continue  # External references are administrator claims, not locally verified.
            if store is None:
                store = RunControlStore(root, read_only=True)
            _check_run_evidence(item, store.get(reference.removeprefix("run:")))
            checked_runs += 1
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "compatibility.json"
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(matrix.model_dump_json(indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        if path.is_symlink():
            raise ValueError("compatibility destination must not be a symlink")
        temporary.replace(path)
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "published": str(path),
        "entries": len(matrix.entries),
        "local_runs_checked": checked_runs,
    }


def benchmark_delivery_action(
    args: argparse.Namespace, registry: AdapterRegistry, root: Path
) -> dict[str, Any]:
    """Dispatch delivery commands without constructing execution stores or leases."""
    if args.benchmark_command == "handoff":
        return _handoff(args, registry, root)
    if args.benchmark_command == "compatibility":
        path = root / "compatibility.json"
        if args.compatibility_command == "show":
            return (
                read_matrix(path).model_dump(mode="json")
                if path.is_file()
                else {"schema_version": 1, "entries": []}
            )
        return _publish_matrix(args, registry, root)
    raise ValueError("unsupported benchmark delivery action")
