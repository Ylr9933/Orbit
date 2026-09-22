"""Read-only scope verification; all mutations belong to native environment teardown."""

import json
import re
import subprocess


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode:
        raise RuntimeError("Docker command failed: " + result.stderr[-1500:])
    return result.stdout


def remaining(project: str) -> list[str]:
    if not re.fullmatch(r"infra_[a-f0-9]{24}__[a-z0-9_]+", project):
        raise ValueError("invalid task-owned Compose project")
    selector = "label=com.docker.compose.project=" + project
    return (
        docker("ps", "-aq", "--filter", selector).split()
        + docker("network", "ls", "-q", "--filter", selector).split()
        + docker("volume", "ls", "-q", "--filter", selector).split()
    )


def inspect_containers(project: str) -> list[dict]:
    ids = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).split()
    return json.loads(docker("inspect", *ids)) if ids else []
