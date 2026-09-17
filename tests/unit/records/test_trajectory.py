"""Trajectory views preserve lineage and exclude evaluator-private observations."""

import hashlib
import json
from datetime import UTC, datetime

from agent_infra.records import (
    AttemptManifest,
    AttemptTrajectoryBuilder,
    DataClass,
    EventDraft,
    ProducerKind,
    RecordContext,
    RunManifest,
    Visibility,
    export_jsonl,
)
from agent_infra.records.local import LocalRecordsStore


def test_build_and_export_versioned_trajectory(tmp_path):
    store = LocalRecordsStore(tmp_path / "records")
    now = datetime.now(UTC)
    store.begin_run(RunManifest("run", now, {"kind": "benchmark"}))
    store.begin_attempt(
        AttemptManifest(
            "attempt",
            "run",
            now,
            "task",
            "sha256:task",
            policy_snapshot={"provider": "codex", "model": "example"},
        )
    )
    user = store.scoped_sink(RecordContext("run", "attempt", "user", ProducerKind.USER))
    agent = store.scoped_sink(RecordContext("run", "attempt", "agent", ProducerKind.AGENT))
    evaluator = store.scoped_sink(
        RecordContext("run", "attempt", "evaluator", ProducerKind.EVALUATOR)
    )
    user.append_events((EventDraft("user.message", {"text": "solve"}),))
    agent.append_events(
        (
            EventDraft("agent.message", {"role": "assistant", "text": "working"}),
            EventDraft(
                "tool.requested",
                {
                    "tool_call_id": "call-1",
                    "tool_name": "shell",
                    "arguments": {"command": "pytest"},
                },
                payload_schema="agent.tool_requested.v1",
                correlation={"tool_call_id": "call-1"},
                span_id="tool-span",
            ),
            EventDraft(
                "tool.completed",
                {"tool_call_id": "call-1", "status": "succeeded", "result": "12 passed"},
                payload_schema="agent.tool_completed.v1",
                correlation={"tool_call_id": "call-1"},
                span_id="tool-span",
            ),
        )
    )
    evaluator.append_events(
        (
            EventDraft(
                "evaluation.private_result",
                {"answer": "hidden"},
                visibility=Visibility.EVALUATOR,
                data_class=DataClass.PRIVATE_EVALUATION,
            ),
            EventDraft("reward.assigned", {"target_id": "attempt", "value": 1.0}),
        )
    )
    store.finish_attempt("attempt", status="completed", result={"status": "completed"})
    store.finish_run("run", status="completed")

    trajectory = AttemptTrajectoryBuilder(store).build("attempt")
    assert len(trajectory.steps) == 2
    assert trajectory.steps[-1].terminated
    assert not trajectory.steps[0].reward_event_ids
    assert len(trajectory.steps[-1].reward_event_ids) == 1
    assert "result_reward_rl_candidate" in trajectory.eligibility.eligible_for
    assert "behavior_logprobs_unavailable" in trajectory.eligibility.limitations
    assert trajectory.eligibility.features["tool_call_correlation"] == "complete"
    assert trajectory.steps[1].action_payload["tool_name"] == "shell"
    assert all(
        event_id in trajectory.source_event_ids
        for step in trajectory.steps
        for event_id in (step.action_event_id, *step.next_observation_event_ids)
    )
    assert len(trajectory.source_event_ids) == 5

    exported = export_jsonl((trajectory,), tmp_path / "export")
    payload = (tmp_path / "export" / exported.records_file).read_bytes()
    assert exported.records_sha256 == "sha256:" + hashlib.sha256(payload).hexdigest()
    row = json.loads(payload)
    assert row["trajectory_id"] == trajectory.trajectory_id
    manifest = json.loads((tmp_path / "export" / exported.manifest_file).read_text())
    assert manifest["trajectory_count"] == 1


def test_parallel_tool_results_follow_their_call_ids(tmp_path):
    store = LocalRecordsStore(tmp_path / "records")
    now = datetime.now(UTC)
    store.begin_run(RunManifest("run", now, {}))
    store.begin_attempt(AttemptManifest("attempt", "run", now))
    agent = store.scoped_sink(RecordContext("run", "attempt", "agent", ProducerKind.AGENT))
    events = agent.append_events(
        (
            EventDraft(
                "tool.requested",
                {"tool_call_id": "call-1", "tool_name": "read_pdf"},
                correlation={"tool_call_id": "call-1"},
                span_id="tool-1",
            ),
            EventDraft(
                "tool.requested",
                {"tool_call_id": "call-2", "tool_name": "search"},
                correlation={"tool_call_id": "call-2"},
                span_id="tool-2",
            ),
            EventDraft(
                "tool.completed",
                {"tool_call_id": "call-1", "result": "paper"},
                correlation={"tool_call_id": "call-1"},
                span_id="tool-1",
            ),
            EventDraft(
                "tool.completed",
                {"tool_call_id": "call-2", "result": "links"},
                correlation={"tool_call_id": "call-2"},
                span_id="tool-2",
            ),
        )
    )
    store.finish_attempt("attempt", status="completed", result={})
    store.finish_run("run", status="completed")

    trajectory = AttemptTrajectoryBuilder(store).build("attempt")

    assert trajectory.steps[0].next_observation_event_ids == (events.identifiers[2],)
    assert trajectory.steps[1].next_observation_event_ids == (events.identifiers[3],)
    assert trajectory.eligibility.features["tool_call_correlation"] == "complete"
