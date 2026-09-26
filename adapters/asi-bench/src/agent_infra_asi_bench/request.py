"""Immutable, non-secret native ASI-Bench request."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ASI_REVISION = "38ab4b5364f1fde5515fef7e9210ff3c9db6a2ba"
BACKEND = "asibench-native-v1"
FEATURES = (
    "durable_operation",
    "bounded_logs",
    "process_group_cleanup",
    "wall_timeout",
    "native_evidence",
    "public_native_score",
    "docker_os",
    "native_codex_trace",
    "docker_telemetry",
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instance_dir: str
    instance_digest: str
    tasks_dir: str
    tasks_digest: str
    scorer_policy_digest: str
    task_id: str
    instance_id: str
    prompt_level: str = Field(pattern=r"^b[1-4]$")
    timeout_seconds: int = Field(gt=0, le=10800)
    mode: Literal["codex_os"]
    model: str = Field(min_length=1)
    effort: Literal["low", "medium", "high", "xhigh"] = Field(
        default="medium", exclude_if=lambda value: value == "medium"
    )
    proxy_url: str = Field(default="", exclude_if=lambda value: value == "")
    docker_network: Literal["bridge", "host"] = Field(
        default="bridge", exclude_if=lambda value: value == "bridge"
    )
