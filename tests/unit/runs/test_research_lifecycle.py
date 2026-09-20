"""Failure-path assertions with explicit fake environment; no Docker or model."""

import pytest

from agent_infra.environments.api import CleanupResult, EnvironmentHandle
from agent_infra.runs.research import ResearchController
from agent_infra.runs.research_store import ResearchStore
from tests.unit.runs.test_controller import REQUEST, setup_controller


class FailedArchiveEnvironment:
    def __init__(self):
        self.prepare_count = 0
        self.clean = True

    def prepare(self, spec):
        self.prepare_count += 1
        return EnvironmentHandle("fixture")

    def cleanup(self, handle):
        return CleanupResult(self.clean)

    def collect(self, handle, destination):
        raise ValueError("explicit archive failure fixture")


def setup(root):
    control, _, _ = setup_controller(root)
    env = FailedArchiveEnvironment()
    research = ResearchController(
        control,
        ResearchStore(root / "controller"),
        env,
        control.records,
        lambda p: {"project": {"project_id": p}},
        lambda image: image,
        lambda sink, options: {},
    )
    token = research.bind("project", "session")["binding"]
    return control, env, research, token


def test_resource_shortage_never_creates_environment(tmp_path):
    control, env, research, token = setup(tmp_path)
    try:
        denied = research.call(
            token, "open", {"image": "fixture", "memory_bytes": 2**30}, "too-big"
        )
        assert "error" in denied
        assert env.prepare_count == 0
        assert not control.resources.active_leases
        assert not control.store.list_runs()
    finally:
        research.close()
        control.close()


def test_cleanup_failure_retains_lease_and_archive_failure_is_separate(tmp_path):
    control, env, research, token = setup(tmp_path)
    try:
        run = research.call(
            token, "open", {"image": "fixture", "memory_bytes": 256 * 1024**2}, "open"
        )
        with pytest.raises(ValueError, match="research close"):
            control.cancel(run["run_id"])
        env.clean = False
        closed = research.call(token, "close", {"run_id": run["run_id"]}, "close1")
        assert not closed["result"]["cleanup_complete"] and not closed["result"]["lease_released"]
        assert control.resources.active_leases and control.quarantined
        with pytest.raises(ValueError, match="quarantined"):
            control.submit("one-shot", REQUEST)
        env.clean = True
        closed = research.call(token, "close", {"run_id": run["run_id"]}, "close2")
        assert closed["result"]["cleanup_complete"] and closed["result"]["lease_released"]
        assert closed["result"]["status"] == "archive_failed"
        assert not closed["result"]["archive_complete"]
        assert not control.resources.active_leases
        assert not control.quarantined
    finally:
        env.clean = True
        research.close()
        control.close()
