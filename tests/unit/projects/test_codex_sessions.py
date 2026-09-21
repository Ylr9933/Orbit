"""Synthetic local rollout coverage; no model or personal session is read."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agent_infra.bootstrap.codex_capture import codex_session_action
from agent_infra.bootstrap.projects import project_action
from agent_infra.records.api import EventQuery
from agent_infra.records.local import LocalRecordsStore


def _line(kind: str, payload: dict[str, object]) -> bytes:
    return (
        json.dumps({"timestamp": "2026-09-21T12:00:00+00:00", "type": kind, "payload": payload})
        + "\n"
    ).encode()


def test_discover_bind_sync_and_notify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "project"
    project = project_action(
        "init", {"directory": str(workspace), "goal": "Test research", "state_dir": str(state)}
    )["project"]
    assert isinstance(project, dict)
    project_id = project["project_id"]
    thread_id = str(uuid4())
    home = tmp_path / "codex-home"
    directory = home / "sessions" / "2026" / "09" / "21"
    directory.mkdir(parents=True)
    file = directory / f"rollout-{thread_id}.jsonl"
    file.write_bytes(
        _line(
            "session_meta",
            {"id": thread_id, "cwd": str(workspace), "timestamp": "2026-09-21T12:00:00+00:00"},
        )
        + _line(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        )
        + _line(
            "response_item",
            {
                "type": "custom_tool_call",
                "call_id": "call-1",
                "name": "functions.exec",
                "input": "private input",
            },
        )
        + _line(
            "response_item",
            {"type": "custom_tool_call_output", "call_id": "call-1", "output": "done"},
        )
    )
    monkeypatch.setenv("CODEX_HOME", str(home))
    options = {"identifier": project_id, "state_dir": str(state)}
    discovery = codex_session_action("discover", options)
    assert [item["thread_id"] for item in discovery["sessions"]] == [thread_id]
    assert discovery["sessions"][0]["bound"] is False

    bound = codex_session_action("bind", options | {"thread_id": thread_id, "max_lines": "2"})
    assert bound["imported_lines"] == 2
    assert bound["has_more"] is True
    continued = codex_session_action("sync", options | {"thread_id": thread_id})
    assert continued["imported_lines"] == 2
    assert continued["has_more"] is False
    records = LocalRecordsStore(state / "controller" / "records")
    attempt = bound["records_attempt_id"]
    events = records.read_events(EventQuery(attempt_id=attempt)).items
    assert [event.event_type for event in events] == [
        "agent.session_started",
        "user.message",
        "tool.requested",
        "tool.completed",
    ]
    assert events[1].payload["text"] == "hello"
    assert events[2].payload["arguments"] == "private input"
    assert events[2].correlation["tool_call_id"] == "call-1"
    assert events[2].span_id == events[3].span_id
    assert all(event.raw_refs for event in events)
    assert codex_session_action("sync", options | {"thread_id": thread_id})["imported_lines"] == 0

    with file.open("ab") as stream:
        stream.write(
            _line(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "answer"}],
                },
            )
        )
        stream.write(b'{"type":"response_item"')
    notification = json.dumps(
        {"type": "agent-turn-complete", "thread-id": thread_id, "cwd": str(workspace)}
    )
    notified = codex_session_action(
        "notify", {"notification": notification, "state_dir": str(state)}
    )
    assert notified["imported_lines"] == 1
    assert notified["has_more"] is True
    assert len(records.read_events(EventQuery(attempt_id=attempt)).items) == 5
    with file.open("ab") as stream:
        stream.write(b',"payload":{"type":"message","role":"assistant"}}\n')
    assert codex_session_action("sync", options | {"thread_id": thread_id})["imported_lines"] == 1


def test_wrong_project_and_symlink_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "project"
    first = project_action(
        "init", {"directory": str(workspace), "goal": "First", "state_dir": str(state)}
    )["project"]
    second = project_action(
        "init", {"directory": str(tmp_path / "other"), "goal": "Second", "state_dir": str(state)}
    )["project"]
    assert isinstance(first, dict) and isinstance(second, dict)
    thread_id = str(uuid4())
    home = tmp_path / "codex-home"
    directory = home / "sessions"
    directory.mkdir(parents=True)
    real = directory / f"rollout-{thread_id}.jsonl"
    real.write_bytes(
        _line(
            "session_meta",
            {"id": thread_id, "cwd": str(workspace), "timestamp": "2026-09-21T12:00:00+00:00"},
        )
    )
    link = directory / "linked.jsonl"
    link.symlink_to(real)
    monkeypatch.setenv("CODEX_HOME", str(home))
    # A second path with the same thread ID is rejected even though the linked file is ignored.
    with pytest.raises(ValueError, match="outside"):
        codex_session_action(
            "bind",
            {"identifier": second["project_id"], "state_dir": str(state), "thread_id": thread_id},
        )
    codex_session_action(
        "bind", {"identifier": first["project_id"], "state_dir": str(state), "thread_id": thread_id}
    )
    with pytest.raises(ValueError, match="not bound"):
        codex_session_action(
            "sync",
            {"identifier": second["project_id"], "state_dir": str(state), "thread_id": thread_id},
        )
