"""Batch boundaries: no partial launch on invalid input; incomplete scores stay visible."""

import argparse
import json
from types import SimpleNamespace

import pytest

from agent_infra.benchmarks.batch import BatchPlan, summarize
from agent_infra.benchmarks.planning import canonical_digest
from agent_infra.bootstrap import benchmark_batch as module


def make_batch():
    body = dict(
        schema_version=1,
        concurrency=6,
        model="gpt-6-sol",
        capability_scope="operator_declared_not_runtime_attested",
        members=[
            dict(
                operation_id=f"op-{i}",
                execution=f"{i}.json",
                execution_digest="sha256:" + str(i) * 64,
                unit_id=f"task-{i}",
            )
            for i in range(2)
        ],
    )
    return BatchPlan.model_validate_json(json.dumps({**body, "digest": canonical_digest(body)}))


def test_batch_rejects_tampering_and_duplicate_operations():
    body = make_batch().model_dump(mode="json")
    body["concurrency"] = 7
    with pytest.raises(ValueError, match="digest mismatch"):
        BatchPlan.model_validate_json(json.dumps(body))
    body["members"][1]["operation_id"] = body["members"][0]["operation_id"]
    body["digest"] = canonical_digest({k: v for k, v in body.items() if k != "digest"})
    with pytest.raises(ValueError, match="duplicate batch"):
        BatchPlan.model_validate_json(json.dumps(body))


def test_summary_keeps_not_submitted_and_does_not_turn_missing_scores_into_zero():
    result = summarize(
        make_batch(),
        [
            dict(
                operation_id="op-0",
                run_id="run",
                state="finished",
                result=dict(execution="failed", evaluation="failed", native_result={}),
            )
        ],
    )
    assert result["finished"] == 1 and result["scored"] == 0
    assert result["failed"] == 1 and result["cancelled"] == 0
    assert result["states"] == {"finished": 1, "not_submitted": 1}
    assert result["runs"][0]["metrics"] == {}
    assert result["official_score"] is None


def test_submit_validates_entire_batch_before_any_launch(tmp_path, monkeypatch):
    batch = make_batch()
    monkeypatch.setattr(module, "_context", lambda _: (batch, object(), argparse.Namespace()))
    validated = []

    def validate(execution, *args):
        validated.append(execution.digest)
        if len(validated) == 2:
            raise ValueError("model mismatch")

    monkeypatch.setattr(module, "_validate_submission", validate)
    monkeypatch.setattr(
        module,
        "read_execution",
        lambda p: SimpleNamespace(digest=batch.members[int(p.stem)].execution_digest),
    )

    def unexpected(*args):
        raise AssertionError("must not submit any member before full preflight")

    monkeypatch.setattr(module, "execution_action", unexpected)
    with pytest.raises(ValueError, match="model mismatch"):
        module.batch_action(
            argparse.Namespace(
                directory=tmp_path, batch_command="submit", allow_native_runtime=True
            )
        )
    assert len(validated) == 2


def test_submit_requires_explicit_runtime_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module, "_context", lambda _: (make_batch(), object(), argparse.Namespace())
    )
    with pytest.raises(ValueError, match="allow-native-runtime"):
        module.batch_action(
            argparse.Namespace(
                directory=tmp_path, batch_command="submit", allow_native_runtime=False
            )
        )


def test_prepare_requires_reviewed_declaration_before_touching_output(tmp_path):
    directory = tmp_path / "batch"
    with pytest.raises(ValueError, match="declare-compatibility"):
        module.batch_action(
            argparse.Namespace(
                directory=directory, batch_command="prepare", declare_compatibility=False
            )
        )
    assert not directory.exists()


def test_terminal_model_error_cancels_pending_without_new_admission(tmp_path, monkeypatch):
    snapshot = {
        "runs": [
            {"run_id": "failed", "state": "finished", "failure_reason": "model_unavailable"},
            {"run_id": "queued", "state": "queued", "failure_reason": None},
        ]
    }
    monkeypatch.setattr(module, "_summary", lambda *_: snapshot)
    calls = []
    monkeypatch.setattr(
        module,
        "execution_action",
        lambda args, _: calls.append((args.benchmark_command, args.run_id)),
    )
    module._refresh_active(tmp_path, make_batch(), object(), argparse.Namespace())
    assert calls == [("cancel", "queued")]
    assert json.loads((tmp_path / "blocked.json").read_text())["reason"] == "model_unavailable"
