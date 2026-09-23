"""Frozen PostTrainBench request passed from planning to the selected backend."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

REVISION = "3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1"
AGENT_VERSION = "posttrain-3ed1d32ff1ec"
BACKEND = "posttrain-htcondor-v1"
FEATURES = (
    "durable_operation",
    "bounded_logs",
    "external_scheduler",
    "native_job_id",
    "gpu_allocation",
    "exclusive_gpu_visibility",
    "scheduler_scoped_cleanup",
    "native_evidence",
    "immutable_model_handoff",
    "large_artifact_reference",
)
BASE_MODELS = (
    "google/gemma-3-4b-pt",
    "Qwen/Qwen3-4B-Base",
    "Qwen/Qwen3-1.7B-Base",
    "HuggingFaceTB/SmolLM3-3B-Base",
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = Field(pattern=r"^(engineering|native)$")
    checkout_root: str
    task: str
    task_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runner_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    agent: str
    agent_config: str
    model_to_train: str
    num_hours: int = Field(gt=0, le=50)
    num_gpus: int = Field(ge=0, le=8)
    request_cpus: int = Field(gt=0, le=128)
    request_memory_mb: int = Field(gt=0, le=524288)
    request_disk_gb: int = Field(gt=0, le=2048)
    timeout_seconds: int = Field(gt=0, le=604800)
    results_root: str = ""
    model_store: str = ""
    scheduler_bin_dir: str = ""
    scheduler_digest: str = Field(default="", pattern=r"^(|sha256:[0-9a-f]{64})$")
    max_model_bytes: int = Field(gt=0, le=2 * 1024**4)

    @field_validator("checkout_root", "task", "results_root", "model_store", "scheduler_bin_dir")
    @classmethod
    def no_nul(cls, value: str) -> str:
        if "\0" in value:
            raise ValueError("path contains NUL")
        return value

    def checkout(self) -> Path:
        return Path(self.checkout_root).resolve()
