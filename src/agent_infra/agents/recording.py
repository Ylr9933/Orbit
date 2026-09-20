"""Shared adapter-to-Records normalization for hosted and imported Agent streams."""

from collections.abc import Mapping
from typing import cast

from agent_infra.agents.api import AgentEvent, AgentEventKind
from agent_infra.records.api import EventDraft


def agent_event_draft(event: AgentEvent, raw_refs: tuple[str, ...]) -> EventDraft:
    mapping = {
        AgentEventKind.SESSION: "agent.session_started",
        AgentEventKind.MESSAGE: "agent.message",
        AgentEventKind.TOOL_CALL: "tool.requested",
        AgentEventKind.TOOL_RESULT: "tool.completed",
        AgentEventKind.USAGE: "model.usage",
        AgentEventKind.COMPLETED: "agent.turn_completed",
        AgentEventKind.ERROR: "agent.error",
        AgentEventKind.UNKNOWN: "agent.native_event",
    }
    canonical = dict(event.canonical)
    canonical_call_id = canonical.get("tool_call_id")
    call_id = (
        canonical_call_id
        if isinstance(canonical_call_id, str) and canonical_call_id
        else _find_call_id(event.payload)
    )
    correlation = {"tool_call_id": call_id} if call_id is not None else {}
    span_id = "span_tool_" + call_id if call_id is not None else None
    return EventDraft(
        mapping[event.kind],
        {
            **canonical,
            "source": {
                "native_sequence": event.native_sequence,
                "part_index": event.part_index,
            },
            "native_type": event.native_type,
            "native": dict(event.payload),
        },
        payload_schema=event.payload_schema,
        producer_sequence=event.sequence,
        correlation=correlation,
        span_id=span_id,
        raw_refs=raw_refs,
        normalizer_name="agent-adapter",
        normalizer_version="2.0.0",
    )


def _find_call_id(payload: Mapping[str, object]) -> str | None:
    for key in ("tool_call_id", "call_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    item = payload.get("item")
    if isinstance(item, Mapping):
        return _find_call_id(cast(Mapping[str, object], item))
    return None
