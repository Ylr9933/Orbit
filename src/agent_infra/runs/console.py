"""Local administrator console application service; no HTTP or database internals."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_infra.agents.presentation import event_text
from agent_infra.records.api import DataClass, EventQuery, RecordsReader, Visibility
from agent_infra.records.catalog import ProjectCatalog
from agent_infra.tasks import build_agent_view, load_task

_HIDDEN = {DataClass.PRIVATE_EVALUATION, DataClass.CREDENTIAL, DataClass.SECRET}
_HIDDEN_VISIBILITY = {Visibility.EVALUATOR, Visibility.ADMIN}
_EVENT_FIELDS = {
    "run.created": ("run_id",),
    "attempt.started": ("attempt_id",),
    "phase.started": ("phase",),
    "phase.finished": ("phase", "status", "exit_code"),
    "phase.failed": ("phase", "status"),
    "task.snapshot": ("task_id", "revision", "mode"),
    "policy.snapshot": ("provider", "placement"),
    "lease.granted": ("status", "request", "node_id"),
    "lease.declined": ("status", "shortages"),
    "lease.released": ("released",),
    "environment.ready": ("phase", "image", "cpu_cores", "memory_bytes", "gpu_count"),
    "environment.cleanup_finished": ("complete",),
    "job.submitted": ("job_id", "cwd", "timeout_seconds"),
    "process.started": ("job_id",),
    "process.exited": ("job_id", "status", "exit_code", "logs_truncated"),
    "job.failed": ("job_id", "status", "error_type"),
    "artifact.committed": ("name", "size_bytes", "missing"),
    "capture.truncated": ("job_id",),
    "capture.gap": ("source", "error_type"),
    "controller.error": ("type",),
    "evaluation.started": ("evaluator_ref",),
    "evaluation.finished": ("evaluator_ref", "feedback"),
    "reward.assigned": ("name", "value", "source"),
}
_AGENT_EVENT_FIELDS = {
    "agent.session_started": ("session_id",),
    "agent.message": ("role", "text"),
    "tool.requested": ("tool_call_id", "tool_name", "tool_type"),
    "tool.completed": ("tool_call_id", "tool_name", "status", "is_error"),
    "model.usage": (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ),
    "agent.turn_completed": ("session_id", "finish_reason"),
    "agent.error": ("error_type", "message"),
}


class ConsoleService:
    def __init__(
        self,
        reader: RecordsReader,
        catalog: ProjectCatalog,
        resources: Callable[[], dict[str, Any]],
        agents: Callable[[], list[dict[str, Any]]],
        task_paths: tuple[Path, ...] = (),
    ) -> None:
        self.reader, self.catalog = reader, catalog
        self.resources, self.agents = resources, agents
        self.task_paths = task_paths

    def tasks(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in self.task_paths:
            key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
            try:
                task = load_task(path)
                view = build_agent_view(task)
                items.append(
                    {
                        "key": key,
                        "task_id": task.task_id,
                        "revision": task.revision,
                        "mode": task.mode,
                        "view": asdict(view),
                        "evaluation": task.evaluation.state.value,
                        "resource_intent": {
                            "state": task.resource_intent.state.value,
                            "constraints": json.loads(task.resource_intent.value_json).get(
                                "constraints", {}
                            ),
                        },
                        "error": None,
                    }
                )
            except (OSError, ValueError):
                items.append({"key": key, "task_id": path.name, "error": "任务无法解析"})
        return items

    def runs(self, offset: int = 0) -> dict[str, Any]:
        rows = self.reader.list_runs(limit=100, offset=offset)
        return {
            "items": [
                {
                    "id": row.manifest.run_id,
                    "status": row.status,
                    "created_at": row.manifest.created_at.isoformat(),
                    "image": row.manifest.request.get("solver_image"),
                }
                for row in rows
            ],
            "next_offset": offset + 100 if len(rows) == 100 else None,
        }

    def run_detail(self, run_id: str) -> dict[str, Any]:
        run = self.reader.get_run(run_id)
        attempts = []
        for attempt in self.reader.list_attempts(run_id):
            result = attempt.result or {}
            attempts.append(
                {
                    "id": attempt.manifest.attempt_id,
                    "status": attempt.status,
                    "started_at": attempt.manifest.started_at.isoformat(),
                    "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                    "coverage": dict(attempt.manifest.coverage),
                    "evaluation_status": result.get("evaluation_status"),
                    "cleanup_complete": result.get("cleanup_complete"),
                    "lease_released": result.get("lease_released"),
                }
            )
        return {"id": run_id, "status": run.status, "attempts": attempts}

    def events(self, attempt_id: str, cursor: str | None) -> dict[str, Any]:
        self.reader.get_attempt(attempt_id)
        items: list[dict[str, Any]] = []
        # Scan a bounded number of pages; never send raw/private records or CAS references.
        for _ in range(10):
            page = self.reader.read_events(EventQuery(attempt_id=attempt_id, limit=100), cursor)
            for event in page.items:
                if event.data_class in _HIDDEN or event.visibility in _HIDDEN_VISIBILITY:
                    continue
                is_agent = event.context.producer_kind.value == "agent"
                fields = (
                    _AGENT_EVENT_FIELDS.get(event.event_type)
                    if is_agent
                    else _EVENT_FIELDS.get(event.event_type)
                )
                if not is_agent and fields is None:
                    continue
                payload = {key: event.payload[key] for key in fields or () if key in event.payload}
                items.append(
                    {
                        "id": event.event_id,
                        "type": event.event_type,
                        "at": event.observed_at.isoformat(),
                        "producer": event.context.producer_kind,
                        "phase_id": event.context.phase_id,
                        "span_id": event.span_id,
                        "capture_status": event.capture_status.value,
                        "text": event_text(event.payload) if is_agent else "",
                        "payload": payload,
                    }
                )
            cursor = page.next_cursor
            if items or cursor is None:
                break
        return {"items": items, "next_cursor": cursor}

    def artifacts(self, attempt_id: str) -> list[dict[str, Any]]:
        self.reader.get_attempt(attempt_id)
        return [
            {
                "id": item.artifact_id,
                "name": item.name,
                "kind": item.kind,
                "size_bytes": item.size_bytes,
                "media_type": item.media_type,
            }
            for item in self.reader.list_artifacts(attempt_id)
            if item.data_class not in _HIDDEN and item.visibility not in _HIDDEN_VISIBILITY
        ]

    def save_project(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"id", "revision", "name", "goal", "status", "milestones", "run_ids", "task_keys"}
        if body.keys() - allowed:
            raise ValueError("未知项目字段")
        name, goal = body.get("name"), body.get("goal", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("项目名称需为 1–120 个字符")
        if not isinstance(goal, str) or len(goal) > 5000:
            raise ValueError("研究目标过长")
        status = body.get("status", "planned")
        if status not in {"planned", "active", "blocked", "completed", "archived"}:
            raise ValueError("无效项目状态")
        milestones = body.get("milestones", [])
        if not isinstance(milestones, list) or len(milestones) > 100:
            raise ValueError("最多 100 个里程碑")
        for item in milestones:
            if (
                not isinstance(item, dict)
                or set(item) != {"title", "done"}
                or not isinstance(item["title"], str)
                or not 1 <= len(item["title"].strip()) <= 200
                or type(item["done"]) is not bool
            ):
                raise ValueError("无效里程碑")
        if len({item["title"] for item in milestones}) != len(milestones):
            raise ValueError("里程碑标题必须唯一")
        run_ids, task_keys = body.get("run_ids", []), body.get("task_keys", [])
        for items in (run_ids, task_keys):
            if (
                not isinstance(items, list)
                or len(items) > 500
                or any(not isinstance(value, str) for value in items)
            ):
                raise ValueError("无效关联列表")
        existing = next((p for p in self.catalog.list_projects() if p["id"] == body.get("id")), {})
        for run_id in set(run_ids) - set(existing.get("run_ids", [])):
            self.reader.get_run(run_id)
        registered = {item["key"] for item in self.tasks()}
        if set(task_keys) - registered - set(existing.get("task_keys", [])):
            raise ValueError("任务未注册")
        identifier = body.get("id")
        revision = body.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise ValueError("无效版本")
        if identifier is not None:
            if not isinstance(identifier, str) or identifier not in {
                item["id"] for item in self.catalog.list_projects()
            }:
                raise KeyError("unknown project")
        elif revision != 0:
            raise ValueError("新项目不能指定旧版本")
        return self.catalog.save(
            {
                "id": identifier or uuid.uuid4().hex,
                "name": name.strip(),
                "goal": goal,
                "status": status,
                "milestones": milestones,
                "run_ids": list(dict.fromkeys(run_ids)),
                "task_keys": list(dict.fromkeys(task_keys)),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            revision,
        )
