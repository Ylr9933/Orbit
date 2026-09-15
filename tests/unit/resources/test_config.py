"""Resource request YAML validation."""

from pathlib import Path

import pytest

from agent_infra.resources.config import load_resource_request, parse_bytes


def test_loads_versioned_request_with_units_and_labels(tmp_path: Path) -> None:
    request_file = tmp_path / "resources.yaml"
    request_file.write_text(
        """
version: 1
request_id: training-1
resources:
  cpu: 2.5
  memory: 8GiB
  gpu:
    count: 1
    min_memory: 16GiB
    device_ids: [GPU-abc]
placement:
  node_labels:
    pool: research
queue:
  wait_timeout: 30m
""".strip()
    )

    request = load_resource_request(request_file)

    assert request.cpu_cores == 2.5
    assert request.memory_bytes == 8 * 1024**3
    assert request.gpu.device_ids == ("GPU-abc",)
    assert request.gpu.min_memory_bytes == 16 * 1024**3
    assert request.labels_dict() == {"pool": "research"}
    assert request.wait_timeout_seconds == 1800


def test_rejects_unknown_fields_instead_of_silently_ignoring_them(tmp_path: Path) -> None:
    request_file = tmp_path / "resources.yaml"
    request_file.write_text(
        """
version: 1
request_id: typo
resources:
  cpu: 2
  memory: 1GiB
  gpus: 1
""".strip()
    )

    with pytest.raises(ValueError, match="unknown resources fields: gpus"):
        load_resource_request(request_file)


def test_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    request_file = tmp_path / "resources.yaml"
    request_file.write_text(
        """
version: 1
request_id: duplicate
resources:
  cpu: 2
  cpu: 8
  memory: 1GiB
""".strip()
    )

    with pytest.raises(ValueError, match="duplicate YAML key: cpu"):
        load_resource_request(request_file)


@pytest.mark.parametrize("value", ["12", "GiB", "-1GiB", 1024, True, None])
def test_byte_quantities_require_explicit_valid_units(value: object) -> None:
    with pytest.raises(ValueError):
        parse_bytes(value, "memory")
