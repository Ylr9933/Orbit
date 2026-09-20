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


def test_compiled_environment_lock_is_bound_and_checked(tmp_path, monkeypatch):
    import time

    from agent_infra.environments.preparation_api import SMOKE_VERSION, TEMPLATE_VERSION, digest
    from agent_infra.environments.preparation_store import EnvironmentCatalog

    compiler, identifier, workspace = setup(tmp_path)
    image = "sha256:" + "1" * 64
    settings = workspace / "configs/experiments/pilot.yaml"
    settings.write_text(
        settings.read_text().replace(
            "image: python:3.12-slim", f"image: {image}\n  lock_id: plan:attempt"
        )
    )
    compiled = compile(compiler, identifier)
    task = compiled["compiled"]["task"]
    request = SubmissionRequest(task["task_id"], task["revision"], "explicit-model", network=True)
    proposal = {"dependencies": [], "source": "user", "reason": "fixture"}
    intent = {"goal": "fixture"}
    lock = {
        "image_id": image,
        "proposal_revision": 1,
        "expires_at": time.time() + 100,
        "template_version": TEMPLATE_VERSION,
        "smoke_version": SMOKE_VERSION,
        "agent": "codex",
        "intent_digest": digest(intent),
        "proposal_digest": digest(proposal),
    }
    catalog = EnvironmentCatalog(tmp_path / "state/controller/preparation")
    plan = {
        "plan_id": "plan",
        "project_id": identifier,
        "intent": intent,
        "proposals": [proposal],
        "attempts": [
            {"attempt_id": "attempt", "status": "ready", "cleanup_complete": True, "lock": lock}
        ],
    }
    catalog.save(plan)
    monkeypatch.setattr(run_preflight, "inspect_local_image", lambda *args, **kwargs: image)
    monkeypatch.setattr(
        run_preflight.CodexAdapter,
        "probe",
        lambda self: AgentProbe("codex", True, "/fake/codex", "0.154.0", True, True),
    )
    prepared = run_preflight.prepare_compiled_run(tmp_path / "state", request)
    assert prepared.lineage["environment_lock"] == lock
    lock["expires_at"] = time.time() - 1
    catalog.save(plan)
    with pytest.raises(ValueError, match="expired"):
        run_preflight.prepare_compiled_run(tmp_path / "state", request)
