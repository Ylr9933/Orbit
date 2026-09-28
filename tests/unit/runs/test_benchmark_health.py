"""Health is diagnostic evidence, not a new scoring or termination authority."""

import json

import pytest

from agent_infra.runs.benchmark_health import evaluation_health, terminal_health


def test_nested_judge_and_runtime_errors_but_not_scientific_rejection():
    score = {
        "schema_version": 2,
        "gate_results": [{"details": {"setup_error": "FileNotFoundError: uv"}}],
        "score_details": [{"details": {"raw_multimodal": {"evaluator_unavailable": True}}}],
        "hard_gates_passed": False,
    }
    health = evaluation_health(score)
    assert health["status"] == "needs_review"
    assert {i["kind"] for i in health["issues"]} == {"judge_unavailable", "missing_dependency"}
    assert health["hard_gates_passed"] is False
    score["gate_results"] = [{"passed": False, "message": "summary mismatch"}]
    score["score_details"] = [{"details": {"error": "geometric mean ratio outside gate"}}]
    assert evaluation_health(score)["status"] == "no_anomaly_detected"
    assert evaluation_health({})["status"] == "unknown"
    assert evaluation_health(None)["status"] == "unknown"
    assert evaluation_health({"schema_version": 3})["status"] == "unknown"


def stream(*events):
    return "\n".join(json.dumps(e) for e in events).encode()


def test_terminal_events_override_no_labels_and_ignore_tool_timeout_text():
    data = stream({"type": "item.completed", "text": "timed out"}, {"type": "turn.completed"})
    health = terminal_health(data, "timeout")
    assert health["status"] == "completed" and health["status_conflict"]
    health = terminal_health(
        stream({"type": "turn.failed", "error": {"message": "You've hit your usage limit"}}),
        "timeout",
    )
    assert health["status"] == "quota_exhausted" and health["status_conflict"]
    assert terminal_health(stream({"type": "turn.failed"}), None)["status"] == "failed"
    assert (
        terminal_health(stream({"type": "turn.completed"}, {"type": "turn.started"}), "completed")[
            "status"
        ]
        == "unknown"
    )


@pytest.mark.parametrize(
    "data", [None, b"", b"broken", b"{}", b"[]", b"\xff", b'{"type":"turn.completed"}\npartial']
)
def test_missing_or_invalid_terminal_evidence_remains_unknown(data):
    assert terminal_health(data, "completed")["status"] == "unknown"
