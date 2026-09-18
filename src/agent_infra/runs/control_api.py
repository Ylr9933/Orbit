"""Transport-neutral local run submission and resolved execution contracts."""

import math
from dataclasses import dataclass
from typing import Any

from agent_infra.agents.api import InstallableCommandAgentAdapter
from agent_infra.resources.api import ResourceRequest
from agent_infra.runs.api import RunRequest


class ControlError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SubmissionRequest:
    task_id: str
    task_revision: str
    model: str
    provider: str = "codex"
    timeout_seconds: float = 600
    network: bool = False
    reasoning_effort: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SubmissionRequest":
        try:
            result = cls(**value)
        except TypeError as error:
            raise ControlError(
                "invalid_request", "supply task_id, task_revision and model"
            ) from error
        for name in ("task_id", "task_revision", "model", "provider"):
            item = getattr(result, name)
            if not isinstance(item, str) or not item.strip() or len(item) > 256 or "\0" in item:
                raise ControlError("invalid_request", f"invalid {name}")
        if (
            type(result.timeout_seconds) not in (int, float)
            or not math.isfinite(result.timeout_seconds)
            or not 0 < result.timeout_seconds <= 86400
            or type(result.network) is not bool
        ):
            raise ControlError(
                "invalid_request", "timeout must be 0–86400 seconds; network must be boolean"
            )
        if result.reasoning_effort is not None and not isinstance(result.reasoning_effort, str):
            raise ControlError("invalid_request", "reasoning_effort must be a string")
        return result


@dataclass(frozen=True, slots=True)
class PreparedRun:
    request: RunRequest
    resources: ResourceRequest
    agent: InstallableCommandAgentAdapter
    lineage: dict[str, Any]
