"""Compose project ownership, local Codex transcript discovery and Records capture."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from agent_infra.agents.codex_rollout import (
    MAX_LINE,
    belongs_to_workspace,
    find_sessions,
    rollout_event,
    session_for_id,
)
from agent_infra.bootstrap.paths import state_root
from agent_infra.projects.codex_sessions import CodexBindingStore
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.service import ProjectService
from agent_infra.records.api import (
    AttemptManifest,
    ProducerKind,
    RecordContext,
    RunManifest,
)
from agent_infra.records.local import LocalRecordsStore


def _record_ids(thread_id: str) -> tuple[str, str]:
    return "host-codex-" + thread_id, "host-codex-attempt-" + thread_id


def _records(state: Path, thread_id: str, project_id: str, started_at: str) -> LocalRecordsStore:
    records = LocalRecordsStore(state / "controller" / "records")
    run_id, attempt_id = _record_ids(thread_id)
    started = datetime.fromisoformat(started_at)
    records.begin_run(
        RunManifest(run_id, started, {"kind": "host_codex_session", "project_id": project_id})
    )
    records.begin_attempt(
        AttemptManifest(
            attempt_id,
            run_id,
            started,
            coverage={"host_agent": "partial", "host_external_actions": "unavailable"},
        )
    )
    return records


def codex_session_action(action: str, options: dict[str, str]) -> dict[str, Any]:
    state = state_root(options.get("state_dir"))
    projects = LocalProjectStore(state / "projects")
    bindings = CodexBindingStore(projects)
    if action == "notify":
        # A user-level Codex notify callback includes the real thread ID and cwd.
        # It only syncs previously authorized bindings; it never auto-attaches.
        notice = json.loads(options["notification"])
        if not isinstance(notice, dict) or notice.get("type") != "agent-turn-complete":
            return {"status": "ignored"}
        thread_id = notice.get("thread-id")
        if not isinstance(thread_id, str):
            return {"status": "ignored"}
        try:
            thread_id = str(UUID(thread_id))
        except ValueError:
            return {"status": "ignored"}
        binding = bindings.get(thread_id)
        cwd = notice.get("cwd")
        if (
            binding is None
            or not isinstance(cwd, str)
            or not Path(cwd)
            .resolve()
            .is_relative_to(Path(projects.get(binding.project_id).project.workspace).resolve())
        ):
            return {"status": "unbound_or_cwd_mismatch"}
        return _sync(state, bindings, thread_id, int(options.get("max_lines", "2000")))

    project = ProjectService(projects).get(options["identifier"])
    workspace = Path(project.workspace)
    if action == "discover":
        candidates = [
            {
                "thread_id": item.thread_id,
                "cwd": item.cwd,
                "started_at": item.started_at,
                "bound": bindings.get(item.thread_id) is not None,
            }
            for item in find_sessions()
            if belongs_to_workspace(item, workspace)
        ]
        candidates.sort(key=lambda item: str(item["started_at"]), reverse=True)
        return {
            "project_id": project.project_id,
            "sessions": candidates[:100],
            "truncated": len(candidates) > 100,
        }

    thread_id = str(UUID(options["thread_id"]))
    if action == "bind":
        session = session_for_id(thread_id)
        if not belongs_to_workspace(session, workspace):
            raise ValueError("Codex session cwd is outside the project workspace")
        bindings.bind(thread_id, project.project_id, session.started_at, session.cwd)
        return _sync(state, bindings, thread_id, int(options.get("max_lines", "2000")))
    if action == "sync":
        binding = bindings.get(thread_id)
        if binding is None or binding.project_id != project.project_id:
            raise ValueError("Codex session is not bound to this project")
        return _sync(state, bindings, thread_id, int(options.get("max_lines", "2000")))
    raise ValueError("unknown Codex session action")


def _sync(
    state: Path, bindings: CodexBindingStore, thread_id: str, max_lines: int
) -> dict[str, Any]:
    if not 1 <= max_lines <= 10_000:
        raise ValueError("max_lines must be between 1 and 10000")
    binding = bindings.get(thread_id)
    if binding is None:
        raise ValueError("Codex session is not bound")
    session = session_for_id(thread_id)
    if (session.cwd, session.started_at) != (binding.cwd, binding.started_at):
        raise ValueError("Codex session metadata changed; capture stopped")
    records = _records(state, thread_id, binding.project_id, binding.started_at)
    run_id, attempt_id = _record_ids(thread_id)
    sink = records.scoped_sink(
        RecordContext(
            run_id, attempt_id, "host-codex:" + thread_id, ProducerKind.AGENT, session_id=thread_id
        )
    )
    offset, line_number = binding.next_offset, binding.next_line
    imported, bytes_read = 0, 0
    with session.path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if size < offset:
            raise ValueError("Codex session was truncated; refusing to skip or relabel history")
        stream.seek(offset)
        while imported < max_lines and bytes_read < 32 * 1024 * 1024:
            raw = stream.readline(MAX_LINE + 1)
            if not raw or not raw.endswith(b"\n"):
                break  # The active writer may not have finished its last line.
            if len(raw) > MAX_LINE:
                raise ValueError("Codex session line exceeds 16 MiB capture limit")
            try:
                row = json.loads(raw)
            except (UnicodeError, ValueError):
                row = {"type": "invalid_json"}
            if not isinstance(row, dict):
                row = {"type": "invalid_json"}
            blob = sink.put_blob(raw, media_type="application/x-ndjson")
            draft = rollout_event(row, line_number, blob.digest, thread_id)
            # Stable identity and monotonic cursor make retries safe after a crash.
            sink.append_events((draft,))
            previous = offset
            offset = stream.tell()
            line_number += 1
            bindings.advance(thread_id, previous, offset, line_number)
            imported += 1
            bytes_read += len(raw)
        stream.seek(0, 2)
        has_more = stream.tell() > offset
    return {
        "project_id": binding.project_id,
        "thread_id": thread_id,
        "records_run_id": run_id,
        "records_attempt_id": attempt_id,
        "imported_lines": imported,
        "next_line": line_number,
        "has_more": has_more,
        "capture_status": "partial",
        "synced_at": datetime.now(UTC).isoformat(),
    }
