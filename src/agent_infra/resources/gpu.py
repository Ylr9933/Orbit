"""Explicit administrative GPU capacity mapped from observed host devices."""

from collections.abc import Sequence

from agent_infra.resources.api import GpuCapacity, HostResourceSnapshot


def authorized_gpus(
    snapshot: HostResourceSnapshot, device_ids: Sequence[str]
) -> tuple[GpuCapacity, ...]:
    """Only explicitly listed, currently observed full GPU UUIDs become capacity."""
    if len(device_ids) != len(set(device_ids)):
        raise ValueError("GPU allowlist contains duplicate device UUIDs")
    observed = {gpu.device_id: gpu for gpu in snapshot.gpus}
    result: list[GpuCapacity] = []
    for device_id in device_ids:
        if not device_id.startswith("GPU-") or device_id not in observed:
            raise ValueError(f"GPU UUID is not present in the host snapshot: {device_id}")
        gpu = observed[device_id]
        result.append(GpuCapacity(gpu.device_id, gpu.index, gpu.name, gpu.memory_total_bytes))
    return tuple(result)
