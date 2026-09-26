"""Immutable local single-trial profile. Native task values are never rewritten."""

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    agent: Literal["oracle", "nop", "codex"] = "oracle"
    model: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$", exclude_if=lambda v: v is None
    )
    codex_version: str | None = Field(
        default=None, pattern=r"^\d+\.\d+\.\d+$", exclude_if=lambda v: v is None
    )
    auth_mode: Literal["host_codex", "api_key"] = Field(
        default="host_codex", exclude_if=lambda v: v == "host_codex"
    )
    effort: Literal["low", "medium", "high", "xhigh"] = Field(
        default="medium", exclude_if=lambda v: v == "medium"
    )
    proxy_url: str | None = Field(default=None, exclude_if=lambda v: v is None)
    api_key_file: str | None = Field(default=None, exclude_if=lambda v: v is None)
    codex_bundle: str | None = Field(default=None, exclude_if=lambda v: v is None)
    codex_bundle_digest: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$", exclude_if=lambda v: v is None
    )
    cpu: float = Field(default=1, gt=0, le=64)
    memory_mb: int = Field(default=2048, gt=0, le=262144)
    source_trial: str | None = None

    @model_validator(mode="after")
    def agent_configuration(self):
        if self.auth_mode == "api_key" and not self.api_key_file:
            raise ValueError("api_key authentication requires a private api_key_file reference")
        if self.api_key_file and (self.auth_mode != "api_key" or self.agent != "codex"):
            raise ValueError("api_key_file requires Codex api_key mode")
        if bool(self.codex_bundle) != bool(self.codex_bundle_digest):
            raise ValueError("codex_bundle and codex_bundle_digest must be provided together")
        if self.codex_bundle and self.agent != "codex":
            raise ValueError("Codex bundle requires agent=codex")
        if self.agent == "codex":
            if not self.model or self.model == "none" or not self.codex_version:
                raise ValueError("Codex requires an explicit model and exact CLI version")
        elif self.model is not None or self.codex_version is not None:
            raise ValueError("oracle/nop cannot carry model configuration")
        return self


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
