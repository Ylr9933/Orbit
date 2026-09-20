"""Compose project context and provider normalization for the research controller."""

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_infra.agents.claude_code import ClaudeCodeAdapter
from agent_infra.agents.codex import CodexAdapter
from agent_infra.agents.deepseek_harness import DeepSeekHarnessAdapter
from agent_infra.agents.recording import agent_event_draft
from agent_infra.bootstrap.projects import project_action
from agent_infra.records.api import CaptureStatus, EventDraft, EventLink, RecordSink


def project_context(state: Path, identifier: str) -> dict[str, Any]:
    return project_action("research-context", {"identifier": identifier, "state_dir": str(state)})


def import_host_trace(sink: RecordSink, options: dict[str, Any]) -> dict[str, Any]:
    adapters: dict[
        str, type[CodexAdapter] | type[ClaudeCodeAdapter] | type[DeepSeekHarnessAdapter]
    ] = {
        "codex": CodexAdapter,
        "claude-code": ClaudeCodeAdapter,
        "dsh": DeepSeekHarnessAdapter,
    }
    provider = options["provider"]
    if provider not in adapters:
        raise ValueError("unsupported trace provider")
    text = options["text"]
    if not isinstance(text, str) or len(text.encode()) > 32768:
        raise ValueError("trace chunk must be at most 32 KiB")
    if len(text.splitlines()) > 1:
        raise ValueError("import one JSONL line per chunk to preserve stable source identity")
    offset = options.get("line_offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("invalid line offset")
    source = options["source_id"]
    if not isinstance(source, str) or not 1 <= len(source) <= 128:
        raise ValueError("supply a stable source_id, preferably the original file digest")
    blob = sink.put_blob(text.encode(), media_type="application/x-ndjson")
    count = 0
    for event in adapters[provider]().decode_events(iter(text.splitlines())):
        draft = agent_event_draft(event, (blob.digest,))
        key = hashlib.sha256(
            (
                f"{provider}:{source}:{offset + (event.native_sequence or 0)}:{event.part_index}"
            ).encode()
        ).hexdigest()
        links: tuple[EventLink, ...] = ()
        arguments = event.canonical.get("arguments")
        if (
            isinstance(arguments, dict)
            and arguments.get("operation_id")
            and options.get("project_id")
        ):
            platform_id = hashlib.sha256(
                f"{options['project_id']}:{sink.context.session_id}:{arguments['operation_id']}".encode()
            ).hexdigest()
            links = (EventLink("platform_tool_call", span_id="tool_" + platform_id),)
        sink.append_events(
            (
                replace(
                    draft,
                    producer_sequence=int(key[:12], 16),
                    links=links,
                    idempotency_key="native:" + sink.context.run_id + ":" + key,
                    correlation=dict(draft.correlation)
                    | {"external_session_id": sink.context.session_id or "", "source_id": source},
                    capture_status=CaptureStatus.PARTIAL,
                ),
            )
        )
        count += 1
    sink.append_events(
        (
            EventDraft(
                "capture.coverage",
                {
                    "scope": "explicit_host_trace_import",
                    "provider": provider,
                    "source_id": source,
                    "platform_external_actions": "partial",
                },
                idempotency_key="coverage:"
                + sink.context.run_id
                + ":"
                + source
                + ":"
                + blob.digest,
                producer_sequence=int(
                    hashlib.sha256((source + blob.digest).encode()).hexdigest()[:12], 16
                ),
                capture_status=CaptureStatus.PARTIAL,
            ),
        )
    )
    return {
        "decoded_events": count,
        "source_id": source,
        "raw_blob": blob.digest,
        "capture_status": "partial",
    }
