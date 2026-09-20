"""Versioned environment intent/proposal contracts, independent of protocols and Docker."""

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any, Protocol

TEMPLATE_VERSION = "python-cpu-v1"
SMOKE_VERSION = "python-smoke-v1"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def strings(value: Any, pattern: str, name: str, *, limit: int = 64) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must be a list of at most {limit} strings")
    if any(not isinstance(s, str) or len(s) > 160 or not re.fullmatch(pattern, s) for s in value):
        raise ValueError(f"invalid {name}")
    if len(set(value)) != len(value):
        raise ValueError(f"duplicate {name}")
    return tuple(sorted(value))


def object_fields(value: Any, allowed: set[str], required: set[str]) -> None:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValueError(
            f"expected object with required {sorted(required)}; allowed {sorted(allowed)}"
        )


@dataclass(frozen=True)
class EnvironmentIntent:
    goal: str
    base_image: str
    template: str = "python-cpu"
    imports: tuple[str, ...] = ()
    allowed_packages: tuple[str, ...] = ()
    agent: str = "none"
    network: bool = False
    cpu: float = 1
    memory_bytes: int = 2 * 1024**3
    max_attempts: int = 3
    total_seconds: int = 600
    attempt_seconds: int = 180
    valid_seconds: int = 86400

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EnvironmentIntent":
        object_fields(value, set(cls.__dataclass_fields__), {"goal", "base_image"})
        data = dict(value)
        data["imports"] = strings(
            data.get("imports", []), r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", "imports"
        )
        names = strings(
            data.get("allowed_packages", []), r"[A-Za-z0-9][A-Za-z0-9._-]*", "allowed_packages"
        )
        data["allowed_packages"] = tuple(sorted({package_name(n) for n in names}))
        result = cls(**data)
        if not isinstance(result.goal, str) or not 1 <= len(result.goal.strip()) <= 2000:
            raise ValueError("goal must contain 1–2000 characters; do not include secrets")
        if (
            not isinstance(result.base_image, str)
            or "://" in result.base_image
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./:@_-]{0,255}", result.base_image)
        ):
            raise ValueError("base_image must be a local image reference, without credentials")
        if result.template not in {"existing", "python-cpu"} or result.agent not in {
            "none",
            "codex",
        }:
            raise ValueError("supported templates: existing/python-cpu; agents: none/codex")
        if type(result.network) is not bool:
            raise ValueError("network must be boolean")
        if type(result.cpu) not in (int, float) or not math.isfinite(result.cpu) or result.cpu <= 0:
            raise ValueError("cpu must be finite and positive")
        if type(result.memory_bytes) is not int or result.memory_bytes < 64 * 1024**2:
            raise ValueError("memory_bytes must be an integer of at least 64 MiB")
        bounds = {
            "max_attempts": (1, 5),
            "total_seconds": (1, 1800),
            "attempt_seconds": (1, 600),
            "valid_seconds": (60, 604800),
        }
        for key, (low, high) in bounds.items():
            item = getattr(result, key)
            if type(item) is not int or not low <= item <= high:
                raise ValueError(f"{key} must be an integer between {low} and {high}")
        return result

    def to_dict(self) -> dict[str, Any]:
        # JSON collections at persistence boundaries.
        return dict(json.loads(json.dumps(asdict(self))))


@dataclass(frozen=True)
class EnvironmentProposal:
    dependencies: tuple[str, ...]
    source: str
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any], intent: EnvironmentIntent) -> "EnvironmentProposal":
        object_fields(
            value, {"dependencies", "source", "reason"}, {"dependencies", "source", "reason"}
        )
        dependencies = strings(
            value["dependencies"],
            r"[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9.+_-]*",
            "dependencies",
        )
        names = [package_name(d.split("==")[0]) for d in dependencies]
        if len(set(names)) != len(names) or set(names) - set(intent.allowed_packages):
            raise ValueError("dependencies must be unique and within intent.allowed_packages")
        if intent.template == "existing" and dependencies:
            raise ValueError("existing template cannot install dependencies")
        if dependencies and not intent.network:
            raise ValueError("installing public wheels requires the intent's network authorization")
        if value["source"] not in {"user", "agent"}:
            raise ValueError("source must be user or agent")
        if not isinstance(value["reason"], str) or not 1 <= len(value["reason"].strip()) <= 2000:
            raise ValueError("reason must contain 1–2000 characters; do not include secrets")
        return cls(dependencies, value["source"], value["reason"])

    def to_dict(self) -> dict[str, Any]:
        return dict(json.loads(json.dumps(asdict(self))))


@dataclass(frozen=True)
class PreparationResult:
    status: str
    image_id: str | None
    cleanup_complete: bool
    details: dict[str, Any]


class EnvironmentPreparer(Protocol):
    def resolve(self, image: str, agent: str = "none") -> str: ...
    def execute(
        self,
        *,
        key: str,
        intent: EnvironmentIntent,
        proposal: EnvironmentProposal,
        base: str,
        cached: dict[str, Any] | None,
        workspace: Path,
        timeout: float,
        cancel: Event,
        emit: Callable[[str, dict[str, Any]], None],
    ) -> PreparationResult: ...
