"""Small provider-neutral helpers for canonical Agent event payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping


def first_string(value: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
    return None


def first_value(value: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def structured_value(value: object) -> object:
    """Deserialize JSON strings when possible while preserving other observed values."""

    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def text_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        texts = []
        for item in value:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, Mapping):
                text = first_string(item, "text", "content")
                if text is not None:
                    texts.append(text)
        return "\n".join(texts) or None
    if isinstance(value, Mapping):
        return first_string(value, "text", "content", "message")
    return None


def usage_payload(payload: Mapping[str, object]) -> dict[str, object]:
    usage = as_mapping(payload.get("usage")) or payload
    input_details = as_mapping(usage.get("input_tokens_details"))
    output_details = as_mapping(usage.get("output_tokens_details"))
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens", "tokens"),
        "cache_read_input_tokens": ("cache_read_input_tokens", "cached_input_tokens"),
        "cache_creation_input_tokens": ("cache_creation_input_tokens",),
        "reasoning_output_tokens": ("reasoning_output_tokens", "reasoning_tokens"),
    }
    result: dict[str, object] = {}
    for target, keys in aliases.items():
        for key in keys:
            item = usage.get(key)
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                result[target] = item
                break
    cached = input_details.get("cached_tokens")
    if "cache_read_input_tokens" not in result and isinstance(cached, int) and cached >= 0:
        result["cache_read_input_tokens"] = cached
    reasoning = output_details.get("reasoning_tokens")
    if "reasoning_output_tokens" not in result and isinstance(reasoning, int) and reasoning >= 0:
        result["reasoning_output_tokens"] = reasoning
    if (
        "total_tokens" not in result
        and {
            "input_tokens",
            "output_tokens",
        }
        <= result.keys()
    ):
        input_tokens = result["input_tokens"]
        output_tokens = result["output_tokens"]
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            result["total_tokens"] = input_tokens + output_tokens
    return result


def error_payload(payload: Mapping[str, object]) -> dict[str, object]:
    error = as_mapping(payload.get("error"))
    source = error or payload
    result: dict[str, object] = {}
    error_type = first_string(source, "type", "error_type", "code")
    message = first_string(source, "message", "error", "text")
    if error_type is not None:
        result["error_type"] = error_type
    if message is not None:
        result["message"] = message
    return result
