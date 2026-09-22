"""Immutable local single-trial profile. Native task values are never rewritten."""

import hashlib
import importlib.metadata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

HARBOR_REVISION = "bac9a80d1d63a0265cf85e8fe18f1b752dad62d7"
BACKEND = "harbor-docker-v1"
FEATURES = (
    "durable_operation",
    "native_trial",
    "separate_verifier",
    "cpu_memory_limits",
    "scoped_container_cleanup",
    "native_evidence",
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: str
    task_digest: str
    agent: str = "oracle"
    # Engineering profile initially admits model-free native agents only.
    cpu: float = Field(default=1, gt=0, le=64)
    memory_mb: int = Field(default=2048, gt=0, le=262144)
    source_trial: str | None = None


def runner_digest() -> str:
    """Pin installed native implementation, not just a reusable release version."""
    dist = importlib.metadata.distribution("harbor")
    if dist.version != "0.23.0":
        raise ValueError("Harbor 0.23.0 from the documented pinned commit is required")
    sha = hashlib.sha256()
    for item in sorted(dist.files or [], key=str):
        if str(item).startswith("harbor/") and not str(item).endswith(".pyc"):
            sha.update(str(item).encode())
            sha.update(Path(dist.locate_file(item)).read_bytes())
    digest = "sha256:" + sha.hexdigest()
    expected = "sha256:e3b6258b9263d9869efd51375ef8d7d6109d974e65c8ddf5cdebd62ef5714176"
    if digest != expected:
        raise ValueError("installed Harbor files do not match the supported pinned build")
    return digest
