"""Persistent authorization bindings and ambiguous-operation retry behavior."""

import pytest

from agent_infra.runs.research_store import ResearchStore


def test_bindings_and_ambiguous_operations_survive_restart(tmp_path):
    store = ResearchStore(tmp_path)
    token = store.bind("project", "session")
    assert store.begin("op", {"action": "start"}) is None
    restarted = ResearchStore(tmp_path)
    assert restarted.binding(token) == ("project", "session")
    with pytest.raises(ValueError, match="interrupted"):
        restarted.begin("op", {"action": "start"})
    with pytest.raises(ValueError, match="different parameters"):
        restarted.begin("op", {"action": "close"})
    restarted.finish("op", {"job_id": "original"})
    assert restarted.begin("op", {"action": "start"}) == {"job_id": "original"}
    with pytest.raises(ValueError, match="binding"):
        restarted.binding("unknown")
