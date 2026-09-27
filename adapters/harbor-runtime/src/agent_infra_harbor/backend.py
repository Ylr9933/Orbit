"""Durable process launch plus positive native container cleanup attestation."""

import json
from dataclasses import replace
from pathlib import Path

from agent_infra.environments.api import CleanupResult, Submission
from agent_infra.environments.execution_api import (
    ExecutionHandle,
    ExecutionObservation,
    ResourceAllocation,
)
from agent_infra.environments.managed_process import ManagedProcessBackend

from .docker import remaining
from .request import BACKEND, FEATURES


class HarborBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_process_group_and_native_compose_projects"

    def observe(self, handle: ExecutionHandle, cursor: int = 0) -> ExecutionObservation:
        observed = super().observe(handle, cursor)
        evidence = Path(self.spec(handle).workspace) / "attestations"
        if evidence.is_symlink():
            raise ValueError("unsafe native allocation directory")
        files = sorted(evidence.glob("*-resources.json")) if evidence.is_dir() else []
        allocation = None
        peaks = []
        for file in files:
            cpu, memory = 0.0, 0
            if file.is_symlink():
                raise ValueError("unsafe native allocation attestation")
            document = json.loads(file.read_bytes())
            for container in document["containers"]:
                cpu += int(container["nano_cpus"]) / 1e9
                memory += int(container["memory_bytes"])
            peaks.append((cpu, memory))
        if peaks:
            allocation = ResourceAllocation(
                max(p[0] for p in peaks),
                max(p[1] for p in peaks),
                0,
                "native-docker-inspect-phase-peak",
            )
        # Parent-process rusage does not measure the child Docker containers.
        return replace(observed, usage=None, allocation=allocation)

    def collect(self, handle: ExecutionHandle) -> Submission:
        spec = self.spec(handle)
        root = Path(spec.workspace)
        if "native-evidence.json" in spec.outputs:
            manifest = root / "native-evidence.json"
            if not manifest.is_file() or manifest.is_symlink():
                raise ValueError("native evidence inventory missing; retain workspace for recovery")
            for path in (root / "trials").rglob("*"):
                if path.name in {"auth.json", ".env"}:
                    raise ValueError("credential-shaped native output cannot enter Records")
        return super().collect(handle)

    def cleanup(self, handle: ExecutionHandle) -> CleanupResult:
        process = super().cleanup(handle)
        if not process.complete:
            return process
        spec = self.spec(handle)
        receipt = Path(spec.workspace) / "native-cleanup.json"
        if not receipt.is_file():
            return CleanupResult(False, "native teardown receipt missing; inspect owned job")
        data = json.loads(receipt.read_bytes())
        if not data.get("complete"):
            return CleanupResult(False, "native teardown was not confirmed")
        try:
            if any(remaining(project) for project in data["projects"]):
                return CleanupResult(False, "native Docker objects still exist")
        except (OSError, RuntimeError):
            return CleanupResult(False, "Docker daemon unavailable; cannot confirm cleanup")
        return CleanupResult(True, self.cleanup_scope)
