"""Versioned trajectory derivation and immutable JSONL export manifests."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_infra.records.api import (
    DataClass,
    EventEnvelope,
    RecordsReader,
    Visibility,
)

TRAJECTORY_SCHEMA_VERSION = "records.trajectory.v2"
TRAJECTORY_BUILDER_NAME = "attempt-event-graph"
TRAJECTORY_BUILDER_VERSION = "2.0.0"

_ACTION_TYPES = frozenset({"agent.message", "tool.requested"})
_OBSERVATION_TYPES = frozenset(
    {
        "user.message",
        "task.snapshot",
        "policy.snapshot",
        "tool.completed",
        "tool.failed",
        "process.exited",
        "agent.tool_result",
    }
)
_REWARD_TYPES = frozenset({"reward.assigned"})


@dataclass(frozen=True, slots=True)
class TrainingEligibility:
    eligible_for: tuple[str, ...]
    limitations: tuple[str, ...]
    features: dict[str, str]


@dataclass(frozen=True, slots=True)
class TrajectoryStep:
    step_index: int
    observation_event_ids: tuple[str, ...]
    action_event_id: str
    action_kind: str
    action_payload: dict[str, object]
    next_observation_event_ids: tuple[str, ...]
    reward_event_ids: tuple[str, ...]
    terminated: bool
    truncated: bool
    termination_reason: str | None
    policy_snapshot_id: str | None
    source_span_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrajectoryView:
    schema_version: str
    trajectory_id: str
    attempt_id: str
    run_id: str
    builder_name: str
    builder_version: str
    built_at: str
    source_event_ids: tuple[str, ...]
    steps: tuple[TrajectoryStep, ...]
    eligibility: TrainingEligibility


@dataclass(frozen=True, slots=True)
class DatasetExport:
    schema_version: str
    export_id: str
    created_at: str
    trajectory_schema: str
    builder_name: str
    builder_version: str
    trajectory_count: int
    records_file: str
    records_sha256: str
    manifest_file: str


class AttemptTrajectoryBuilder:
    """Build conservative, observable event-level trajectories from one Attempt."""

    name = TRAJECTORY_BUILDER_NAME
    version = TRAJECTORY_BUILDER_VERSION

    def __init__(self, reader: RecordsReader) -> None:
        self._reader = reader

    def build(self, attempt_id: str) -> TrajectoryView:
        attempt = self._reader.get_attempt(attempt_id)
        trace = self._reader.read_trace(attempt_id)
        visible = tuple(event for event in trace.events if _eligible_source_event(event))
        rewards = tuple(event for event in visible if event.event_type in _REWARD_TYPES)
        actions = tuple(event for event in visible if event.event_type in _ACTION_TYPES)
        tool_actions = tuple(event for event in actions if event.event_type == "tool.requested")
        tool_results = tuple(
            event for event in visible if event.event_type in {"tool.completed", "tool.failed"}
        )
        policy_event = next(
            (event for event in reversed(visible) if event.event_type == "policy.snapshot"),
            None,
        )
        policy_snapshot = (
            policy_event.payload if policy_event is not None else attempt.manifest.policy_snapshot
        )
        policy_snapshot_id = _policy_snapshot_id(policy_snapshot)
        steps: list[TrajectoryStep] = []
        previous_action_index = -1
        event_positions = {event.event_id: index for index, event in enumerate(visible)}
        for step_index, action in enumerate(actions):
            position = event_positions[action.event_id]
            next_position = (
                event_positions[actions[step_index + 1].event_id]
                if step_index + 1 < len(actions)
                else len(visible)
            )
            observations = tuple(
                event.event_id
                for event in visible[previous_action_index + 1 : position]
                if event.event_type in _OBSERVATION_TYPES
            )
            next_observation_events = tuple(
                event
                for event in visible[position + 1 : next_position]
                if event.event_type in _OBSERVATION_TYPES
            )
            if action.event_type == "tool.requested":
                next_observation_events = tuple(
                    event
                    for event in next_observation_events
                    if event.event_type not in {"tool.completed", "tool.failed"}
                )
            correlated_tool_results = (
                _matching_tool_results(action, tool_results)
                if action.event_type == "tool.requested"
                else ()
            )
            next_observations = tuple(
                dict.fromkeys(
                    event.event_id for event in (*next_observation_events, *correlated_tool_results)
                )
            )
            scoped_rewards = tuple(
                event.event_id
                for event in rewards
                if _reward_targets(
                    event,
                    action,
                    attempt_id,
                    terminal_step=step_index == len(actions) - 1,
                )
            )
            terminal = step_index == len(actions) - 1 and attempt.finished_at is not None
            status = attempt.status if terminal else None
            steps.append(
                TrajectoryStep(
                    step_index,
                    observations,
                    action.event_id,
                    action.event_type,
                    dict(action.payload),
                    next_observations,
                    scoped_rewards,
                    terminal and status == "completed",
                    terminal and status in {"cancelled", "timed_out"},
                    status if terminal and status != "completed" else None,
                    policy_snapshot_id,
                    tuple(
                        dict.fromkeys(
                            span
                            for span in (
                                action.span_id,
                                *(event.span_id for event in next_observation_events),
                                *(event.span_id for event in correlated_tool_results),
                            )
                            if span is not None
                        )
                    ),
                )
            )
            previous_action_index = position
        gaps = any(
            event.event_type in {"capture.gap", "capture.truncated"} for event in trace.events
        )
        uses = ["analysis"]
        limitations = ["behavior_logprobs_unavailable"]
        if actions:
            uses.append("sft_candidate")
        else:
            limitations.append("no_agent_actions")
        if rewards and actions:
            uses.append("result_reward_rl_candidate")
        else:
            limitations.append("terminal_reward_unavailable")
        if gaps:
            limitations.append("capture_incomplete")
        if not tool_actions:
            tool_correlation = "unavailable"
        elif all(
            _tool_call_id(action) is not None and _matching_tool_results(action, tool_results)
            for action in tool_actions
        ):
            tool_correlation = "complete"
        else:
            tool_correlation = "partial"
            limitations.append("tool_call_correlation_partial")
        features = {
            "observation": "partial" if actions else "unavailable",
            "action": "complete" if actions else "unavailable",
            "token_ids": "unavailable",
            "behavior_logprobs": "unavailable",
            "terminal_reward": "present" if rewards else "absent",
            "private_evaluation_filtered": "true",
            "capture": "partial" if gaps else "complete",
            "tool_call_correlation": tool_correlation,
        }
        source_ids = tuple(event.event_id for event in visible)
        stable = hashlib.sha256(
            (attempt_id + "\0" + self.version + "\0" + "\0".join(source_ids)).encode()
        ).hexdigest()
        return TrajectoryView(
            TRAJECTORY_SCHEMA_VERSION,
            "trajectory_" + stable,
            attempt_id,
            attempt.manifest.run_id,
            self.name,
            self.version,
            datetime.now(UTC).isoformat(),
            source_ids,
            tuple(steps),
            TrainingEligibility(tuple(uses), tuple(limitations), features),
        )


def export_jsonl(trajectories: tuple[TrajectoryView, ...], destination: Path) -> DatasetExport:
    """Write a fixed export plus a digest-bearing manifest using atomic replacements."""

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    export_id = "export_" + uuid.uuid4().hex
    records_name = "trajectories.jsonl"
    manifest_name = "manifest.json"
    lines = tuple(
        json.dumps(asdict(item), ensure_ascii=False, sort_keys=True, allow_nan=False)
        for item in trajectories
    )
    payload = (("\n".join(lines) + "\n") if lines else "").encode()
    digest = hashlib.sha256(payload).hexdigest()
    created_at = datetime.now(UTC).isoformat()
    result = DatasetExport(
        "records.dataset_export.v1",
        export_id,
        created_at,
        TRAJECTORY_SCHEMA_VERSION,
        TRAJECTORY_BUILDER_NAME,
        TRAJECTORY_BUILDER_VERSION,
        len(trajectories),
        records_name,
        "sha256:" + digest,
        manifest_name,
    )
    records_temporary = destination / (records_name + ".tmp")
    records_temporary.write_bytes(payload)
    _sync(records_temporary)
    records_temporary.replace(destination / records_name)
    manifest_temporary = destination / (manifest_name + ".tmp")
    manifest_temporary.write_text(
        json.dumps(asdict(result), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    _sync(manifest_temporary)
    manifest_temporary.replace(destination / manifest_name)
    return result


def _tool_call_id(event: EventEnvelope) -> str | None:
    value = event.correlation.get("tool_call_id")
    if isinstance(value, str) and value:
        return value
    payload_value = event.payload.get("tool_call_id")
    return payload_value if isinstance(payload_value, str) and payload_value else None


def _matching_tool_results(
    action: EventEnvelope, results: tuple[EventEnvelope, ...]
) -> tuple[EventEnvelope, ...]:
    call_id = _tool_call_id(action)
    if call_id is not None:
        return tuple(result for result in results if _tool_call_id(result) == call_id)
    if action.span_id is not None:
        return tuple(result for result in results if result.span_id == action.span_id)
    return ()


def _eligible_source_event(event: EventEnvelope) -> bool:
    return event.visibility is not Visibility.EVALUATOR and event.data_class not in {
        DataClass.PRIVATE_EVALUATION,
        DataClass.CREDENTIAL,
        DataClass.SECRET,
    }


def _reward_targets(
    reward: EventEnvelope,
    action: EventEnvelope,
    attempt_id: str,
    *,
    terminal_step: bool,
) -> bool:
    target = reward.payload.get("target_id")
    if target in {None, attempt_id}:
        return terminal_step
    return target in {action.event_id, action.span_id}


def _policy_snapshot_id(snapshot: object) -> str | None:
    if not snapshot:
        return None
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    return "policy_" + hashlib.sha256(encoded).hexdigest()


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
