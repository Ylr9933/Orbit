import pytest

from agent_infra.resources.api import (
    AllocationStatus,
    LeaseCapacity,
    PersistentLeaseState,
    ResourceClaim,
)
from agent_infra.resources.persistent import PersistentLeaseStore


def claim(identifier: str, *, cpu: float = 1, memory: int = 1024) -> ResourceClaim:
    return ResourceClaim(
        request_id="request-" + identifier,
        owner_id="run-" + identifier,
        backend="native-test",
        cpu_cores=cpu,
        memory_bytes=memory,
        gpu_count=0,
        allocator="local",
    )


def test_lease_is_idempotent_persistent_and_blocks_oversubscription(tmp_path):
    capacity = LeaseCapacity(max_concurrent=1, cpu_cores=2, memory_bytes=4096, gpu_count=0)
    store = PersistentLeaseStore(tmp_path, capacity)
    first = store.acquire(claim("one"))
    assert first.status is AllocationStatus.GRANTED
    assert first.lease is not None and first.lease.owner_epoch == 1
    assert store.acquire(claim("one")) == first

    reopened = PersistentLeaseStore(tmp_path, capacity)
    waiting = reopened.acquire(claim("two"))
    assert waiting.status is AllocationStatus.WAITING
    assert waiting.shortages[0].resource == "concurrency_slots"

    bound = reopened.bind_native(
        first.lease.lease_id,
        first.lease.owner_epoch,
        backend="native-test",
        native_id="job-123",
    )
    assert bound.state is PersistentLeaseState.ACTIVE and bound.native_id == "job-123"
    released = reopened.release(bound.lease_id, bound.owner_epoch, cleanup_confirmed=True)
    assert released.state is PersistentLeaseState.RELEASED
    assert reopened.acquire(claim("two")).status is AllocationStatus.GRANTED


def test_unsatisfiable_and_stale_owner_fail_closed(tmp_path):
    store = PersistentLeaseStore(
        tmp_path, LeaseCapacity(cpu_cores=1, memory_bytes=1024, gpu_count=0)
    )
    decision = store.acquire(claim("large", cpu=2))
    assert decision.status is AllocationStatus.UNSATISFIABLE
    assert decision.shortages[0].resource == "cpu_cores"

    granted = store.acquire(claim("small"))
    assert granted.lease is not None
    lease = granted.lease
    try:
        store.release(lease.lease_id, lease.owner_epoch + 1, cleanup_confirmed=True)
    except ValueError as error:
        assert "stale" in str(error)
    else:
        raise AssertionError("stale owner epoch was accepted")
    assert store.get(lease.lease_id).state is PersistentLeaseState.ALLOCATED


def test_reconciling_or_unconfirmed_cleanup_never_releases_capacity(tmp_path):
    store = PersistentLeaseStore(tmp_path)
    lease = store.acquire(claim("one")).lease
    assert lease is not None
    marked = store.reconcile(lease.lease_id, lease.owner_epoch, "backend unreachable")
    assert marked.state is PersistentLeaseState.RECONCILING
    try:
        store.release(lease.lease_id, lease.owner_epoch, cleanup_confirmed=False)
    except ValueError as error:
        assert "positive cleanup" in str(error)
    else:
        raise AssertionError("unconfirmed cleanup released a lease")
    assert store.acquire(claim("two")).status is AllocationStatus.WAITING


def test_configured_concurrency_survives_restart_and_never_exceeds_numeric_capacity(tmp_path):
    store = PersistentLeaseStore(tmp_path)
    capacity = LeaseCapacity(max_concurrent=3, cpu_cores=2, memory_bytes=4096, gpu_count=0)
    store.configure(capacity)
    restarted = PersistentLeaseStore(tmp_path)
    assert restarted.capacity == capacity
    assert store.capacity == capacity
    first = restarted.acquire(claim("one", cpu=1)).lease
    second = restarted.acquire(claim("two", cpu=1)).lease
    assert first is not None and second is not None
    waiting = restarted.acquire(claim("three", cpu=1))
    assert waiting.status is AllocationStatus.WAITING
    assert waiting.shortages[0].resource == "cpu_cores"
    with pytest.raises(ValueError, match="drain"):
        restarted.configure(LeaseCapacity(max_concurrent=4))
    restarted.release(first.lease_id, first.owner_epoch, cleanup_confirmed=True)
    restarted.release(second.lease_id, second.owner_epoch, cleanup_confirmed=True)
    assert restarted.configure(LeaseCapacity(max_concurrent=2)) == LeaseCapacity(max_concurrent=2)
    assert store.capacity == LeaseCapacity(max_concurrent=2)
    assert store.acquire(claim("later-one")).status is AllocationStatus.GRANTED
    assert store.acquire(claim("later-two")).status is AllocationStatus.GRANTED
    assert store.acquire(claim("later-three")).status is AllocationStatus.WAITING
