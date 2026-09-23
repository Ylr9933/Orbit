"""Fault-window tests: no native benchmarks, models, Docker or actual child processes."""

import importlib
from pathlib import Path

import pytest

from agent_infra.benchmarks.api import AdapterIdentity, PlanRequest
from agent_infra.benchmarks.execution import prepare_execution, validate_backend
from agent_infra.benchmarks.planning import freeze_plan
from agent_infra.benchmarks.registry import LoadedAdapter
from agent_infra.contracts.files import content_digest
from agent_infra.environments.api import CleanupResult, Submission
from agent_infra.environments.execution_api import (
    ExecutionHandle,
    ExecutionObservation,
    Reconciliation,
)
from agent_infra.environments.managed_process import ManagedProcessBackend
from agent_infra.records.api import EventQuery
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources.api import LeaseCapacity
from agent_infra.resources.persistent import PersistentLeaseStore
from agent_infra.runs.benchmark_execution import BenchmarkExecutionService
from agent_infra.runs.control_store import RunControlStore

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/benchmark-execution"


class Backend:
    backend_id = ManagedProcessBackend.backend_id
    features = ManagedProcessBackend.features
    cleanup_scope = "fake_process_group"

    def __init__(self, root):
        self.root, self.calls, self.handle = root, 0, None
        self.handles = {}
        self.lost_reply, self.unknown, self.clean, self.collect_error = False, False, True, False
        self.log = b"native stdout\n\xffraw-byte"
        self.cancelled = False

    def submit(self, operation_id, spec):
        self.calls += 1
        self.handle = ExecutionHandle(operation_id, self.backend_id, "fake-native-1", spec.digest())
        self.handles[operation_id] = self.handle
        if self.lost_reply:
            raise ConnectionError("reply lost after submit")
        return self.handle

    def reconcile(self, operation_id):
        if self.unknown:
            return Reconciliation("unknown", self.handle, "native service unreachable")
        return (
            Reconciliation("known", self.handles[operation_id])
            if operation_id in self.handles
            else Reconciliation("not_submitted")
        )

    def observe(self, handle, cursor=0):
        data = self.log[cursor : cursor + 3]
        return ExecutionObservation(
            "unknown" if self.unknown else "completed",
            0,
            data,
            cursor + len(data),
            cursor + len(data) == len(self.log),
            False,
            CleanupResult(self.clean),
        )

    def cancel(self, handle):
        self.cancelled = True
        return CleanupResult(False)

    def cleanup(self, handle):
        return CleanupResult(self.clean, "fake process group receipt")

    def collect(self, handle):
        if self.collect_error:
            raise OSError("disk unavailable")
        self.root.mkdir(exist_ok=True)
        (self.root / "result.txt").write_text("synthetic result")
        return Submission(self.root, content_digest(self.root), ("result.txt",), ())


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    adapter = importlib.import_module("agent_infra_benchmark_process_example").Adapter()
    loaded = LoadedAdapter(
        adapter,
        AdapterIdentity(
            distribution="agent-infra-benchmark-process-example",
            version="0.1.0",
            entry_point="process-demo",
            adapter_id="process-demo",
            sdk_version="1.0",
        ),
    )
    request = PlanRequest.model_validate_json((EXAMPLE / "request.json").read_bytes())
    frozen = freeze_plan(loaded, EXAMPLE / "fixture", request)
    execution = prepare_execution(frozen, loaded)
    store, records = RunControlStore(tmp_path / "state"), LocalRecordsStore(tmp_path / "records")
    backend = Backend(tmp_path / "fake-outputs")
    return execution, store, records, backend, tmp_path / "workspaces"


def service(context):
    _, store, records, backend, workspace = context
    return BenchmarkExecutionService(store, records, backend, workspace)


def test_lost_submit_reply_recovers_without_relaunch(context):
    execution, store, records, backend, _ = context
    backend.lost_reply = True
    run = service(context).submit("one", execution)
    assert run["state"] == "quarantined" and backend.calls == 1
    # A new coordinator resumes the same native operation from durable control/Records data.
    done = service(context).status(run["run_id"])
    assert done["state"] == "finished" and not done["slot_held"] and backend.calls == 1
    assert done["result"]["evaluation"] == "not_interpreted"
    repeated = service(context).submit("one", execution)
    assert repeated == done and backend.calls == 1
    assert len(records.list_artifacts(run["attempt_id"])) == 1
    events = records.read_events(EventQuery(run_id=run["run_id"])).items
    assert len(events) == 5 and events[-1].event_type == "execution.slot_released"
    assert store.unfinished() == []


def test_unknown_native_service_blocks_replay_and_queues_new_operation(context):
    execution, _, _, backend, _ = context
    backend.lost_reply = True
    run = service(context).submit("one", execution)
    backend.unknown = True
    assert service(context).status(run["run_id"])["slot_held"]
    assert service(context).submit("one", execution)["state"] == "quarantined"
    second = service(context).submit("two", execution)
    assert second["state"] == "queued" and second["queue_position"] == 1
    assert backend.calls == 1


def test_fifo_waiter_starts_after_positive_cleanup_and_restart(context):
    execution, store, records, backend, workspace = context
    backend.clean = False
    first = service(context).submit("one", execution)
    assert first["state"] == "quarantined"
    second = service(context).submit("two", execution)
    assert second["state"] == "queued" and backend.calls == 1

    backend.clean = True
    assert service(context).status(first["run_id"])["state"] == "finished"
    restarted = BenchmarkExecutionService(store, records, backend, workspace)
    done = restarted.status(second["run_id"])
    assert done["state"] == "finished" and backend.calls == 2
    assert done["lease_state"] == "released"


def test_crash_after_lease_commit_recovers_without_oversubscription(context, monkeypatch):
    execution, store, _, backend, _ = context
    scheduler = service(context)
    original = store.update
    fired = False

    def crash(run_id, **fields):
        nonlocal fired
        if "lease_id" in fields and not fired:
            fired = True
            raise OSError("crash after lease commit")
        return original(run_id, **fields)

    monkeypatch.setattr(store, "update", crash)
    with pytest.raises(OSError, match="after lease commit"):
        scheduler.submit("one", execution)
    assert backend.calls == 0
    leases = scheduler.leases.list()
    assert len(leases) == 1 and leases[0].state.value == "allocated"

    done = service(context).status(store.unfinished()[0]["run_id"])
    assert done["state"] == "finished" and backend.calls == 1
    assert len(service(context).leases.list()) == 1


def test_queued_cancel_never_calls_backend(context):
    execution, _, _, backend, _ = context
    backend.clean = False
    service(context).submit("one", execution)
    second = service(context).submit("two", execution)
    cancelled = service(context).status(second["run_id"], cancel=True)
    assert cancelled["state"] == "finished"
    assert cancelled["result"]["cleanup_scope"] == "never_launched"
    assert backend.calls == 1


def test_cleanup_must_be_positive_before_collection_or_release(context):
    execution, _, records, backend, _ = context
    backend.clean = False
    run = service(context).submit("one", execution)
    assert run["state"] == "quarantined" and run["slot_held"]
    assert records.list_artifacts(run["attempt_id"]) == ()
    backend.clean = True
    assert service(context).status(run["run_id"])["state"] == "finished"
    assert backend.calls == 1


def test_collection_failure_retains_slot_then_retries_only_collection(context):
    execution, _, _, backend, _ = context
    backend.collect_error = True
    run = service(context).submit("one", execution)
    assert run["state"] == "collecting" and run["slot_held"]
    backend.collect_error = False
    done = service(context).status(run["run_id"])
    assert done["state"] == "finished" and backend.calls == 1


def test_cursor_commit_failure_replays_bytes_without_duplication(context, monkeypatch):
    execution, store, records, backend, _ = context
    original = store.update
    fired = False

    def crash(run_id, **fields):
        nonlocal fired
        if "cursor" in fields and not fired:
            fired = True
            raise OSError("crash after raw append before cursor commit")
        return original(run_id, **fields)

    monkeypatch.setattr(store, "update", crash)
    with pytest.raises(OSError):
        service(context).submit("one", execution)
    run = store.unfinished()[0]
    done = service(context).status(run["run_id"])
    assert done["result"]["stream"]["size_bytes"] == len(backend.log)
    assert backend.calls == 1
    assert len(records.list_artifacts(run["attempt_id"])) == 1


def test_records_completion_commit_gap_recovers_idempotently(context, monkeypatch):
    execution, store, records, backend, _ = context
    original = store.update
    fired = False

    def crash(run_id, **fields):
        nonlocal fired
        if fields.get("state") == "finished" and not fired:
            fired = True
            raise OSError("crash after Records completion")
        return original(run_id, **fields)

    monkeypatch.setattr(store, "update", crash)
    run = service(context).submit("one", execution)
    assert run["state"] == "collecting"
    done = service(context).status(run["run_id"])
    assert done["state"] == "finished" and backend.calls == 1
    assert done["lease_state"] == "released"
    assert len(records.list_artifacts(run["attempt_id"])) == 1


def test_reconcile_does_not_launch_an_unsubmitted_intent(context):
    execution, store, _, backend, _ = context
    run = store.create(
        "one", {"kind": "benchmark", "execution": execution.model_dump(mode="json")}, {}
    )
    assert service(context).reconcile()[0]["state"] == "accepted"
    assert backend.calls == 0
    cancelled = service(context).status(run["run_id"], cancel=True)
    assert cancelled["state"] == "finished" and backend.calls == 0
    assert cancelled["result"]["cleanup_scope"] == "never_launched"


def test_operation_conflict_and_runtime_capabilities_fail_closed(context):
    execution, _, _, backend, _ = context
    service(context).submit("one", execution)
    changed = execution.model_copy(update={"digest": "sha256:" + "1" * 64})
    with pytest.raises(ValueError, match="different parameters"):
        service(context).submit("one", changed)
    with pytest.raises(ValueError, match="capabilities"):
        validate_backend(execution, backend.backend_id, ())


def test_configured_two_slot_fifo_and_shared_budget_survive_restart(context):
    execution, store, records, backend, workspace = context
    capacity = PersistentLeaseStore(store.path.parent / "leases")
    capacity.configure(LeaseCapacity(max_concurrent=2))
    backend.clean = False
    first = service(context).submit("one", execution, budget_group="trial", budget_wall_seconds=60)
    second = service(context).submit("two", execution, budget_group="trial", budget_wall_seconds=60)
    third = service(context).submit(
        "three", execution, budget_group="trial", budget_wall_seconds=60
    )
    assert first["state"] == second["state"] == "quarantined"
    assert backend.calls == 2
    assert third["state"] == "finished"
    assert third["result"]["native_result"]["reason"] == "budget group wall-time limit exhausted"
    assert len([item for item in capacity.list() if item.state.value != "released"]) == 2
    backend.clean = True
    restarted = BenchmarkExecutionService(store, records, backend, workspace)
    assert restarted.status(first["run_id"])["state"] == "finished"
    assert restarted.status(second["run_id"])["state"] == "finished"
    assert backend.calls == 2


def test_conflicting_budget_group_limit_rejected_before_persisting(context):
    execution, store, _, _, _ = context
    service(context).submit("one", execution, budget_group="trial", budget_wall_seconds=60)
    with pytest.raises(ValueError, match="conflicting limits"):
        service(context).submit("two", execution, budget_group="trial", budget_wall_seconds=30)
    assert len(store.ordered()) == 1


def test_three_jobs_admit_in_fifo_order_at_two_authorized_slots(context):
    execution, store, records, backend, workspace = context
    leases = PersistentLeaseStore(store.path.parent / "leases")
    leases.configure(LeaseCapacity(max_concurrent=2))
    backend.clean = False
    first = service(context).submit("one", execution)
    second = service(context).submit("two", execution)
    third = service(context).submit("three", execution)
    assert [first["state"], second["state"], third["state"]] == [
        "quarantined",
        "quarantined",
        "queued",
    ]
    assert third["queue_position"] == 1 and backend.calls == 2
    backend.clean = True
    restarted = BenchmarkExecutionService(store, records, backend, workspace)
    assert restarted.status(first["run_id"])["state"] == "finished"
    done = restarted.status(third["run_id"])
    assert done["state"] == "finished" and backend.calls == 3
    assert restarted.status(second["run_id"])["state"] == "finished"
