"""Bounded repair, crash accounting and shared admission using an explicit fake backend."""

import time
from threading import Event

import pytest

from agent_infra.environments.preparation_api import PreparationResult
from agent_infra.environments.preparation_store import EnvironmentCatalog
from agent_infra.runs.environment_preparation import EnvironmentPreparation
from tests.unit.runs.test_controller import REQUEST, setup_controller


class FakePreparer:
    def __init__(self, status="ready", cleanup=True, wait=False):
        self.status, self.cleanup, self.wait = status, cleanup, wait
        self.calls = []
        self.started = Event()

    def resolve(self, image, agent="none"):
        return "sha256:" + "1" * 64

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        if self.wait:
            kwargs["cancel"].wait(5)
        return PreparationResult(
            "cancelled" if kwargs["cancel"].is_set() else self.status,
            self.resolve("image"),
            self.cleanup,
            {"cache_hit": bool(kwargs["cached"])},
        )


def setup(root, backend, **intent):
    control, _, _ = setup_controller(root)
    catalog = EnvironmentCatalog(root / "preparation")
    service = EnvironmentPreparation(control, catalog, backend)
    service.call(
        "project",
        "session",
        "environment_plan",
        {"intent": {"goal": "CPU", "base_image": "python", "memory_bytes": 256 * 1024**2} | intent},
        "plan",
    )
    service.call(
        "project",
        "session",
        "environment_propose",
        {
            "plan_id": "plan",
            "expected_revision": 0,
            "proposal": {"dependencies": [], "source": "agent", "reason": "fixture"},
        },
        "proposal",
    )
    return control, catalog, service


def build(service, key):
    return service.call(
        "project", "session", "environment_build", {"plan_id": "plan", "revision": 1}, key
    )


def finished(catalog):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = catalog.get("project", "plan")
        if value["attempts"][-1]["status"] != "running":
            return value
        time.sleep(0.01)
    pytest.fail("preparation worker did not finish")


def test_permanent_failure_spends_attempts_and_shares_resource_slot(tmp_path):
    backend = FakePreparer(status="failed")
    control, catalog, service = setup(tmp_path, backend, max_attempts=2)
    try:
        for number in range(2):
            build(service, str(number))
            plan = finished(catalog)
            assert plan["attempts"][-1]["lock"] is None
        with pytest.raises(ValueError, match="budget exhausted"):
            build(service, "third")
        assert len(backend.calls) == 2
        assert not control.resources.active_leases
    finally:
        service.close()
        control.close()


def test_cancel_and_exclusive_slot(tmp_path):
    backend = FakePreparer(wait=True)
    control, catalog, service = setup(tmp_path, backend)
    try:
        accepted = build(service, "first")
        assert backend.started.wait(3)
        with pytest.raises(ValueError, match="already active"):
            control.submit("overlap", REQUEST)
        with pytest.raises(ValueError, match="bound"):
            control.cancel(accepted["attempts"][-1]["run_id"])
        with pytest.raises(ValueError, match="busy"):
            build(service, "overlap")
        service.call("project", "session", "environment_cancel", {"plan_id": "plan"}, "stop")
        plan = finished(catalog)
        assert plan["attempts"][-1]["status"] == "cancelled"
        assert plan["attempts"][-1]["cleanup_complete"]
        assert not control.resources.active_leases
    finally:
        service.close()
        control.close()


def test_cleanup_failure_retains_lease_and_never_locks(tmp_path):
    control, catalog, service = setup(tmp_path, FakePreparer(cleanup=False))
    try:
        build(service, "fail-cleanup")
        attempt = finished(catalog)["attempts"][-1]
        assert attempt["lock"] is None
        assert control.resources.active_leases and control.quarantined
    finally:
        service.close()
        assert not control.close()


def test_ready_lock_invalidation_and_recovery_budget(tmp_path):
    control, catalog, service = setup(tmp_path, FakePreparer())
    try:
        build(service, "success")
        plan = finished(catalog)
        lock = plan["attempts"][-1]["lock"]["lock_id"]
        assert service.resolve("project", lock)["image_id"].startswith("sha256:")
        plan["proposals"].append(plan["proposals"][0])
        catalog.save(plan)
        with pytest.raises(ValueError, match="proposal changed"):
            service.resolve("project", lock)
        plan["attempts"].append(
            {"attempt_id": "crash", "status": "running", "reserved_seconds": 600}
        )
        plan["reserved_seconds"] = 600
        catalog.save(plan)
        service.close()
        recovered = EnvironmentPreparation(control, catalog, FakePreparer())
        assert catalog.get("project", "plan")["attempts"][-1]["status"] == "interrupted"
        with pytest.raises(ValueError, match="budget exhausted"):
            recovered.call(
                "project",
                "session",
                "environment_build",
                {"plan_id": "plan", "revision": 2},
                "again",
            )
        recovered.close()
    finally:
        service.close()
        control.close()


def test_recording_failure_quarantines_before_publishing_readiness(tmp_path, monkeypatch):
    control, catalog, service = setup(tmp_path, FakePreparer())

    def fail(*args, **kwargs):
        raise OSError("fixture full evidence disk")

    monkeypatch.setattr(control.records, "finish_attempt", fail)
    try:
        build(service, "evidence-failure")
        deadline = time.monotonic() + 5
        while not control.quarantined and time.monotonic() < deadline:
            time.sleep(0.01)
        assert control.quarantined
        attempt = catalog.get("project", "plan")["attempts"][-1]
        assert attempt["lock"] is None
        with pytest.raises(ValueError, match="quarantined"):
            control.submit("must-not-start", REQUEST)
    finally:
        service.close()
        assert not control.close()
