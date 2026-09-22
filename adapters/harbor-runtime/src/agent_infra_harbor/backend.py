"""Durable process launch plus positive native container cleanup attestation."""

import json
from pathlib import Path

from agent_infra.environments.api import CleanupResult
from agent_infra.environments.execution_api import ExecutionHandle
from agent_infra.environments.managed_process import ManagedProcessBackend

from .docker import remaining
from .request import BACKEND, FEATURES


class HarborBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_process_group_and_native_compose_projects"

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
