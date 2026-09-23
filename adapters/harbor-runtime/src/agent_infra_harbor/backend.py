"""Durable process launch plus positive native container cleanup attestation."""

import json
from dataclasses import replace
from pathlib import Path

from agent_infra.environments.api import CleanupResult
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
        if len(files) == 1:
            cpu, memory = 0.0, 0
            file = files[0]
            if file.is_symlink():
                raise ValueError("unsafe native allocation attestation")
            document = json.loads(file.read_bytes())
            for container in document["containers"]:
                cpu += int(container["nano_cpus"]) / 1e9
                memory += int(container["memory_bytes"])
            allocation = ResourceAllocation(cpu, memory, 0, "native-docker-inspect")
        # Parent-process rusage does not measure the child Docker containers.
        return replace(observed, usage=None, allocation=allocation)

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
