"""Small validated values for evidence-backed research and bounded execution."""

import hashlib
import json
import math
from typing import Any

from agent_infra.projects.api import ProjectError, require_text


def document(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - keys:
        raise ProjectError(f"{name} must be an object with only {sorted(keys)}")
    if len(json.dumps(value, allow_nan=False).encode()) > 256 * 1024:
        raise ProjectError(f"{name} exceeds 256 KiB")
    return value


def text(value: Any, name: str) -> str:
    require_text(value, name, 20000)
    return str(value)


def identifier(value: Any) -> str:
    require_text(value, "operation_id", 128)
    return str(value)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def items(value: Any, name: str, maximum: int = 100) -> list[Any]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ProjectError(f"{name} requires 1–{maximum} entries")
    return value


def number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ProjectError(f"{name} must be finite, between {minimum} and {maximum}")
    return float(value)


def pointer(value: Any, path: str) -> Any:
    """RFC 6901 traversal; never evaluate an expression or load a host path."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ProjectError("metric pointer must be a nonempty JSON pointer")
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(part)] if isinstance(value, list) else value[part]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ProjectError(f"metric pointer not found: {path}") from error
    number(value, "metric value", -1e300, 1e300)
    return value
