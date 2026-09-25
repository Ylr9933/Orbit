"""Durable native process backend with task-owned Docker child cleanup."""

import subprocess

from agent_infra.environments.api import CleanupResult
from agent_infra.environments.execution_api import ExecutionHandle
from agent_infra.environments.managed_process import ManagedProcessBackend

from .docker_proxy import OWNER_LABEL
from .request import BACKEND, FEATURES, Request


class AsiBenchBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES + ("docker_os", "native_codex_trace", "docker_telemetry")
    cleanup_scope = "owned_process_group"

    def cleanup(self, handle: ExecutionHandle) -> CleanupResult:
        process = super().cleanup(handle)
        if not process.complete:
            return process
        spec = self.spec(handle)
        if spec.command.argv[1:3] != ("-m", "agent_infra_asi_bench.runner"):
            return process
        request = Request.model_validate_json(spec.command.argv[-1])
        if request.mode != "codex_os":
            return process
        run_id = spec.run_id
        try:
            listed = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"label={OWNER_LABEL}={run_id}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            for container_id in listed.stdout.splitlines():
                details = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        f'{{{{index .Config.Labels "{OWNER_LABEL}"}}}}',
                        container_id,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                if details.stdout.strip() != run_id:
                    return CleanupResult(False, "Docker ownership mismatch")
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )
            return CleanupResult(True, "scope: owned process group and labeled Docker containers")
        except (OSError, subprocess.SubprocessError):
            return CleanupResult(False, "owned Docker container cleanup unconfirmed")


class CodexAsiBenchBackend(AsiBenchBackend):
    """Same native backend contract with explicit child-container cleanup scope."""

    cleanup_scope = "owned_process_group_and_labeled_docker_containers"
