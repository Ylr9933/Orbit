"""Only native Codex execution is supported; evidence and ownership remain enforced."""

import json
from types import SimpleNamespace

import pytest
from agent_infra_asi_bench import Adapter
from agent_infra_asi_bench.backend import CodexAsiBenchBackend
from agent_infra_asi_bench.request import Request
from pydantic import ValidationError

from agent_infra.environments.api import CleanupResult
from agent_infra.environments.managed_process import ManagedProcessBackend


@pytest.mark.parametrize("mode", [None, "fixture"])
def test_legacy_fixture_request_is_rejected(mode):
    payload = {
        "instance_dir": "/instance",
        "instance_digest": "digest",
        "tasks_dir": "/tasks",
        "tasks_digest": "digest",
        "scorer_policy_digest": "digest",
        "task_id": "task",
        "instance_id": "instance",
        "prompt_level": "b1",
        "timeout_seconds": 60,
        "model": "none",
    }
    if mode is not None:
        payload["mode"] = mode
    with pytest.raises(ValidationError):
        Request.model_validate(payload)


def test_codex_cleanup_refuses_unowned_container(tmp_path, monkeypatch):
    monkeypatch.setattr(ManagedProcessBackend, "cleanup", lambda *_: CleanupResult(True, "done"))
    request = {
        "instance_dir": "/instance",
        "instance_digest": "digest",
        "tasks_dir": "/tasks",
        "tasks_digest": "digest",
        "scorer_policy_digest": "digest",
        "task_id": "task",
        "instance_id": "instance",
        "prompt_level": "b1",
        "timeout_seconds": 60,
        "mode": "codex_os",
        "model": "gpt-5.6-sol",
    }
    spec = SimpleNamespace(
        run_id="owned",
        command=SimpleNamespace(
            argv=("python", "-m", "agent_infra_asi_bench.runner", json.dumps(request))
        ),
    )
    monkeypatch.setattr(CodexAsiBenchBackend, "spec", lambda *_: spec)
    calls = []

    def docker(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="container-id\n" if command[1] == "ps" else "someone-else\n")

    monkeypatch.setattr("agent_infra_asi_bench.backend.subprocess.run", docker)
    assert not CodexAsiBenchBackend(tmp_path / "backend").cleanup(None).complete
    assert [call[1] for call in calls] == ["ps", "inspect"]


def test_missing_native_summary_still_exposes_archived_evidence(tmp_path):
    evidence = tmp_path / "outputs" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "index.json").write_text(
        json.dumps(
            {"capture_status": "partial", "files": {}, "trajectory": {"session_id": "session"}}
        )
    )
    result = Adapter().interpret(tmp_path)
    assert result["evaluation"] == "unknown"
    assert result["evidence"]["trajectory"]["session_id"] == "session"
