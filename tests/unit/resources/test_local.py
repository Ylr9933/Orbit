"""Single-node admission, shortage, concurrency, and release behavior."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from agent_infra.resources import (
    AllocationStatus,
    GpuCapacity,
    GpuObservation,
    GpuRequest,
    HostResourceSnapshot,
    LocalResourceManager,
    NodeCapacity,
    ResourceRequest,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)
GIB = 1024**3


def _capacity() -> NodeCapacity:
    return NodeCapacity(
        node_id="node-a",
        cpu_cores=4,
        memory_bytes=16 * GIB,
        gpus=(GpuCapacity("GPU-a", 0, "Test GPU", 24 * GIB),),
        labels=(("pool", "research"),),
    )


def _snapshot(*, processes: int = 0, captured_at: datetime = NOW) -> HostResourceSnapshot:
    return HostResourceSnapshot(
        node_id="node-a",
        captured_at=captured_at,
        cpu_logical_cores=8,
        cpu_utilization_percent=20,
        load_average_1m=1,
        memory_total_bytes=32 * GIB,
        memory_available_bytes=20 * GIB,
        gpus=(GpuObservation("GPU-a", 0, "Test GPU", 24 * GIB, 20 * GIB, 0, processes),),
    )


def _request(request_id: str, *, cpu: float = 2, gpu_count: int = 0) -> ResourceRequest:
    return ResourceRequest(
        request_id=request_id,
        cpu_cores=cpu,
        memory_bytes=4 * GIB,
        gpu=GpuRequest(count=gpu_count, min_memory_bytes=16 * GIB),
        node_labels=(("pool", "research"),),
    )


def test_grants_idempotently_then_releases_idempotently() -> None:
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW, id_factory=lambda: "lease-1")
    manager.update_snapshot(_snapshot())

    first = manager.try_allocate(_request("run-1", gpu_count=1))
    repeated = manager.try_allocate(_request("run-1", gpu_count=1))

    assert first.status is AllocationStatus.GRANTED
    assert repeated.lease == first.lease
    assert first.lease is not None
    assert first.lease.gpu_device_ids == ("GPU-a",)
    assert manager.release("lease-1") is True
    assert manager.release("lease-1") is False


def test_impossible_request_is_not_left_waiting() -> None:
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW)

    decision = manager.try_allocate(_request("too-large", cpu=8))

    assert decision.status is AllocationStatus.UNSATISFIABLE
    assert decision.shortages[0].resource == "cpu_cores"


def test_external_gpu_process_causes_temporary_wait() -> None:
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW)
    manager.update_snapshot(_snapshot(processes=1))

    decision = manager.try_allocate(_request("gpu-busy", gpu_count=1))

    assert decision.status is AllocationStatus.WAITING
    assert decision.shortages[-1].resource == "gpus"


def test_stale_snapshot_causes_temporary_wait() -> None:
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW)
    manager.update_snapshot(_snapshot(captured_at=NOW - timedelta(minutes=1)))

    decision = manager.try_allocate(_request("stale"))

    assert decision.status is AllocationStatus.WAITING
    assert decision.shortages[0].resource == "telemetry"


def test_concurrent_requests_cannot_oversubscribe_cpu() -> None:
    ids = iter(["lease-1", "lease-2"])
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW, id_factory=lambda: next(ids))
    manager.update_snapshot(_snapshot())

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(manager.try_allocate, [_request("one"), _request("two")]))

    assert sorted(decision.status for decision in decisions) == [
        AllocationStatus.GRANTED,
        AllocationStatus.GRANTED,
    ]
    third = manager.try_allocate(_request("three", cpu=1))
    assert third.status is AllocationStatus.WAITING


def test_reusing_request_id_with_different_resources_is_rejected() -> None:
    manager = LocalResourceManager(_capacity(), clock=lambda: NOW, id_factory=lambda: "lease-1")
    manager.update_snapshot(_snapshot())
    manager.try_allocate(_request("same"))

    with pytest.raises(ValueError, match="different resource request"):
        manager.try_allocate(_request("same", cpu=1))
