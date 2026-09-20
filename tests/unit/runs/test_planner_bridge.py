"""Untrusted mailbox paths and scoped actions never turn into host path access."""

import json
import os

import pytest

from agent_infra.runs.planner_bridge import PlannerBridge


def test_mailbox_receipts_and_response_symlink(tmp_path):
    calls = []
    bridge = PlannerBridge(tmp_path, lambda action, options: calls.append(action) or options)
    outside = tmp_path.parent / "sentinel"
    outside.write_text("unchanged")
    (tmp_path / "response.json").symlink_to(outside)
    request = {"id": "one", "action": "status", "options": {"value": 1}}
    (tmp_path / "request.json").write_text(json.dumps(request))
    assert bridge.poll()["response"]["result"] == {"value": 1}
    assert bridge.poll() is None
    assert calls == ["status"] and outside.read_text() == "unchanged"
    assert not (tmp_path / "response.json").is_symlink()


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversize"])
def test_mailbox_rejects_special_or_large_files(tmp_path, kind):
    path = tmp_path / "request.json"
    if kind == "symlink":
        path.symlink_to("/etc/passwd")
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"x" * 60001)
    with pytest.raises((OSError, ValueError)):
        PlannerBridge(tmp_path, lambda *args: pytest.fail("must not dispatch")).poll()


def test_companion_recording_failure_cannot_be_cleared_by_other_cleanup(tmp_path):
    from agent_infra.resources.api import ResourceRequest
    from tests.unit.runs.test_controller import setup_controller

    control, _, _ = setup_controller(tmp_path)
    try:
        lease = control.allocate_companion(ResourceRequest("planner", 0.25, 64 * 1024**2))
        control.release_research("unrelated", clean=True)
        assert not control.quarantined  # a managed live companion is legitimate
        control.release_companion(lease.lease_id, clean=True)
        control.release_companion(
            lease.lease_id, clean=False
        )  # evidence commit failed after cleanup
        control.release_research("unrelated", clean=True)
        assert control.quarantined
        control.reconcile()
        assert not control.quarantined
    finally:
        control.close()
