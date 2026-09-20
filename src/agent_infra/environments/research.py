"""Long-lived jobs on the existing Docker isolation/ownership implementation."""

import json
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from agent_infra.environments.api import (
    CleanupResult,
    EnvironmentHandle,
    InputMount,
    ProcessCommand,
    SandboxSpec,
    Submission,
)
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.job_api import JobSpec

_CLIENT = """import socket,sys
s=socket.socket(socket.AF_UNIX); s.settimeout(10)
s.connect('/tmp/agent-infra-research.sock')
s.sendall(sys.stdin.buffer.read()+b'\\n')
with s.makefile('rb') as f:
    sys.stdout.buffer.write(f.readline(24*1024*1024))
"""


class DockerResearchEnvironment:
    def __init__(self, docker: DockerEnvironment) -> None:
        self.docker = docker

    def prepare(self, spec: SandboxSpec) -> EnvironmentHandle:
        runtime = Path(__file__).with_name("_research_runtime.py")
        handle = self.docker.prepare(
            replace(
                spec,
                readonly_inputs=spec.readonly_inputs
                + (InputMount(runtime, "/inputs/research-runtime.py"),),
            )
        )
        self.docker.start(
            handle,
            ProcessCommand(
                ("python3", "-I", "-u", "/inputs/research-runtime.py"),
                timeout_seconds=7 * 86400,
            ),
        )
        for _ in range(30):
            try:
                self._request(handle, {"action": "health"})
                return handle
            except RuntimeError:
                time.sleep(0.1)
        raise RuntimeError("research runtime did not start; image must provide Python 3")

    def _request(self, handle: EnvironmentHandle, request: dict[str, Any]) -> dict[str, Any]:
        response = json.loads(
            self.docker.execute_control(
                handle,
                ("python3", "-I", "-c", _CLIENT),
                json.dumps(request),
            )
        )
        if "error" in response:
            raise ValueError(response["error"])
        return dict(response)

    def start_job(self, handle: EnvironmentHandle, spec: JobSpec) -> dict[str, Any]:
        return self._request(handle, asdict(spec) | {"action": "start"})

    def job(self, handle: EnvironmentHandle, job_id: str, *, stop: bool = False) -> dict[str, Any]:
        return self._request(handle, {"action": "stop" if stop else "status", "job_id": job_id})

    def logs(self, handle: EnvironmentHandle, job_id: str, cursor: int) -> dict[str, Any]:
        return self._request(handle, {"action": "logs", "job_id": job_id, "cursor": cursor})

    def file(
        self, handle: EnvironmentHandle, operation: str, path: str, **options: Any
    ) -> dict[str, Any]:
        return self._request(
            handle, options | {"action": "file", "operation": operation, "path": path}
        )

    def cleanup(self, handle: EnvironmentHandle) -> CleanupResult:
        return self.docker.cleanup(handle)

    def collect(self, handle: EnvironmentHandle, destination: Path) -> Submission:
        return self.docker.collect_workspace(handle, destination)
