"""Pinned Harbor environment extension: limits/ownership on every created service."""

import asyncio
import json
from pathlib import Path

from harbor.environments.docker.docker import DockerEnvironment

from agent_infra.environments.recovery import write_ownership

from .docker import inspect_containers, remaining

# Set once by the dedicated native worker, never by the solver.
CONTEXT: dict = {}
ENVIRONMENTS: list = []


class OwnedDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._environment_docker_compose_path.exists():
            raise ValueError("multi-service task Compose is not admitted by this profile")
        self.project = self.session_id.lower()
        self.claimed = False
        self.launch_uncertain = False
        self.limits = {
            "main": (
                self.task_env_config.cpus or CONTEXT["cpu"],
                self.task_env_config.memory_mb or CONTEXT["memory_mb"],
            )
        }
        if self._enable_egress_control:
            self.limits[self._EGRESS_CONTROL_SERVICE_NAME] = (0.1, 128)
        evidence_dir = Path(CONTEXT["root"]) / "attestations"
        evidence_dir.mkdir(exist_ok=True)
        self.overlay = evidence_dir / (self.project + ".json")
        self.overlay.write_text(
            json.dumps(
                {
                    "services": {
                        name: {
                            "cpus": cpu,
                            "mem_limit": f"{memory}m",
                            "labels": {"agent-infra.owner": CONTEXT["owner"]},
                        }
                        for name, (cpu, memory) in self.limits.items()
                    }
                }
            )
        )
        ENVIRONMENTS.append(self)
        write_ownership(
            Path(CONTEXT["root"]) / "native-ownership.json",
            {"projects": [env.project for env in ENVIRONMENTS], "owner": CONTEXT["owner"]},
        )

    @property
    def _docker_compose_paths(self):
        return [*super()._docker_compose_paths, self.overlay]

    async def _run_docker_compose_command(self, command, *args, **kwargs):
        # Cancellation must not race an outstanding daemon-side container creation.
        if command[0] not in {"up", "create", "run"}:
            return await super()._run_docker_compose_command(command, *args, **kwargs)
        pending = asyncio.create_task(super()._run_docker_compose_command(command, *args, **kwargs))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(asyncio.shield(pending), timeout=20)
            except TimeoutError:
                self.launch_uncertain = True
                pending.cancel()
            except Exception:
                pass  # The command returned a definite failure; creation is no longer pending.
            raise

    async def start(self, force_build: bool):
        if remaining(self.project):
            raise RuntimeError("owned namespace already exists; refusing native down/up replay")
        self.claimed = True
        await super().start(force_build)
        containers = inspect_containers(self.project)
        seen = set()
        evidence = []
        for item in containers:
            labels = item["Config"]["Labels"]
            service = labels["com.docker.compose.service"]
            cpu, memory = self.limits[service]
            host = item["HostConfig"]
            if (
                labels.get("agent-infra.owner") != CONTEXT["owner"]
                or host["NanoCpus"] != int(cpu * 1e9)
                or host["Memory"] != memory * 1024**2
                or host.get("DeviceRequests")
            ):
                raise RuntimeError("Docker resource/ownership attestation failed")
            seen.add(service)
            evidence.append(
                {
                    "id": item["Id"],
                    "service": service,
                    "nano_cpus": host["NanoCpus"],
                    "memory_bytes": host["Memory"],
                    "image": item["Image"],
                }
            )
        if seen != set(self.limits):
            raise RuntimeError("Docker service set differs from the admitted profile")
        write_ownership(
            Path(CONTEXT["root"]) / "attestations" / (self.project + "-resources.json"),
            {
                "project": self.project,
                "containers": evidence,
                "disk_enforcement": "native_docker_not_supported",
            },
        )

    async def stop(self, delete: bool):
        if not self.claimed:
            return
        # A build may fail before Compose has a complete configuration or any objects.
        if not remaining(self.project):
            return
        # Do not use Harbor's --rmi local: images can be shared with unrelated trials.
        await self._run_docker_compose_command(["down", "--volumes", "--remove-orphans"])
        if remaining(self.project):
            raise RuntimeError("native Compose cleanup incomplete")


async def close_all():
    errors = []
    for env in reversed(ENVIRONMENTS):
        try:
            await asyncio.wait_for(env.stop(delete=True), timeout=30)
        except Exception as error:
            errors.append(error)
    if errors:
        raise ExceptionGroup("native cleanup incomplete", errors)
