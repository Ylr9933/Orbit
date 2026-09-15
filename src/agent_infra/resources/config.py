"""Strict versioned YAML loading for resource requests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import Any

import yaml

from agent_infra.resources.api import GpuRequest, ResourceRequest

_BYTE_UNITS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def load_resource_request(path: Path) -> ResourceRequest:
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("resource YAML must not exceed 1 MiB")
    try:
        document = yaml.compose(text, Loader=yaml.SafeLoader)
        if document is not None:
            _reject_duplicate_keys(document)
        payload = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid resource YAML: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("resource YAML root must be a mapping")
    _only_keys(payload, {"version", "request_id", "resources", "placement", "queue"}, "root")
    if payload.get("version") != 1:
        raise ValueError("resource YAML version must be 1")

    resources = _mapping(payload.get("resources"), "resources")
    _only_keys(resources, {"cpu", "memory", "gpu"}, "resources")
    gpu_payload = _mapping(resources.get("gpu", {}), "resources.gpu")
    _only_keys(
        gpu_payload,
        {"count", "min_memory", "vendor", "device_ids"},
        "resources.gpu",
    )
    device_ids = _string_tuple(gpu_payload.get("device_ids", ()), "resources.gpu.device_ids")
    count = _integer(gpu_payload.get("count", len(device_ids)), "resources.gpu.count")

    placement = _mapping(payload.get("placement", {}), "placement")
    _only_keys(placement, {"node_labels"}, "placement")
    labels_payload = _mapping(placement.get("node_labels", {}), "placement.node_labels")
    labels = tuple(
        sorted(
            (str(key), _string(value, f"node label {key}")) for key, value in labels_payload.items()
        )
    )

    queue = _mapping(payload.get("queue", {}), "queue")
    _only_keys(queue, {"wait_timeout"}, "queue")

    return ResourceRequest(
        request_id=_string(payload.get("request_id"), "request_id"),
        cpu_cores=_positive_number(resources.get("cpu"), "resources.cpu"),
        memory_bytes=parse_bytes(resources.get("memory"), "resources.memory"),
        gpu=GpuRequest(
            count=count,
            min_memory_bytes=parse_bytes(
                gpu_payload.get("min_memory", "0B"),
                "resources.gpu.min_memory",
                allow_zero=True,
            ),
            vendor=_string(gpu_payload.get("vendor", "nvidia"), "resources.gpu.vendor"),
            device_ids=device_ids,
        ),
        node_labels=labels,
        wait_timeout_seconds=parse_duration(queue.get("wait_timeout", 0), "queue.wait_timeout"),
    )


def parse_bytes(value: object, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a byte quantity")
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?[Bb])\s*", value)
        if match is None:
            raise ValueError(f"{field} must use a unit such as GiB or MiB")
        result = int(float(match.group(1)) * _BYTE_UNITS[match.group(2).lower()])
    else:
        raise ValueError(f"{field} must be a byte quantity")
    minimum = 0 if allow_zero else 1
    if result < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field} must be {qualifier}")
    return result


def parse_duration(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a duration")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd])\s*", value.lower())
        if match is None:
            raise ValueError(f"{field} must use a unit such as s, m, h, or d")
        result = float(match.group(1)) * _DURATION_UNITS[match.group(2)]
    else:
        raise ValueError(f"{field} must be a duration")
    if not isfinite(result) or result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return value


def _only_keys(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"unknown {field} fields: {', '.join(unknown)}")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field} must be a list")
    return tuple(_string(item, field) for item in value)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _reject_duplicate_keys(node: yaml.Node) -> None:
    if isinstance(node, yaml.MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                identity = (key_node.tag, key_node.value)
                if identity in seen:
                    raise ValueError(f"duplicate YAML key: {key_node.value}")
                seen.add(identity)
            _reject_duplicate_keys(key_node)
            _reject_duplicate_keys(value_node)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _reject_duplicate_keys(item)
