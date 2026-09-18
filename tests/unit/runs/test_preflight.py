"""Public C -> D boundary: resolve immutable bundles, never start Docker in preflight."""

from dataclasses import replace

import pytest

from agent_infra.agents.api import AgentProbe
from agent_infra.bootstrap import run_preflight
from agent_infra.runs.control_api import ControlError, SubmissionRequest
from tests.unit.projects.test_compilation import compile, setup


def test_compiled_preflight_preserves_snapshot_and_rejects_drift(tmp_path, monkeypatch):
    compiler, identifier, workspace = setup(tmp_path)
    compiled = compile(compiler, identifier)
    task = compiled["compiled"]["task"]
    request = SubmissionRequest(task["task_id"], task["revision"], "explicit-model", network=True)
    monkeypatch.setattr(
        run_preflight, "inspect_local_image", lambda *args, **kwargs: "sha256:image"
    )
    monkeypatch.setattr(
        run_preflight.CodexAdapter,
        "probe",
        lambda self: AgentProbe("codex", True, "/fake/codex", "0.154.0", True, True),
    )
    prepared = run_preflight.prepare_compiled_run(tmp_path / "state", request)
    assert prepared.lineage["project_id"] == identifier
    assert prepared.request.resolved_image == "sha256:image"
    assert (
        prepared.request.expected_snapshot.definition_digest
        == task["snapshot"]["definition_digest"]
    )
    assert not (tmp_path / "state/controller").exists()
    (workspace / "data/raw/input.csv").write_text("original project changes do not affect bundle")
    assert (
        run_preflight.prepare_compiled_run(tmp_path / "state", request).lineage == prepared.lineage
    )
    prepared.request.resource_file.write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        run_preflight.prepare_compiled_run(tmp_path / "state", request)


def test_explicit_provider_network_and_request_shape():
    request = SubmissionRequest("task", "revision", "model")
    with pytest.raises(ControlError, match="network"):
        run_preflight.prepare_compiled_run(None, request)
    with pytest.raises(ControlError, match="supports codex"):
        run_preflight.prepare_compiled_run(None, replace(request, provider="claude-code"))
    for value in (
        {"unknown": 1},
        {"task_id": "x", "task_revision": "y", "model": "z", "timeout_seconds": float("nan")},
    ):
        with pytest.raises(ControlError):
            SubmissionRequest.from_dict(value)
