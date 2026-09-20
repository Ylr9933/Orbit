"""Canonical JSON and timestamp conversion shared by the local reader and writer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


def _now() -> datetime:
    return datetime.now(UTC)


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("record timestamps must include a timezone")
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"record value is not JSON-compatible: {type(value).__name__}")


def _dumps(value: object) -> str:
    return json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _mapping(value: str) -> dict[str, object]:
    result = json.loads(value)
    if not isinstance(result, dict):
        raise RuntimeError("stored record is not a JSON object")
    return cast(dict[str, object], result)


def _strings(value: str) -> tuple[str, ...]:
    result = json.loads(value)
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise RuntimeError("stored record is not a string list")
    return tuple(result)
