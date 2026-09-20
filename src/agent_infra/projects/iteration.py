"""Durable authorization and submission saga; execution remains in the existing Run controller."""

import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from agent_infra.projects._iteration_store import IterationStore
from agent_infra.projects.api import ProjectConflict, ProjectError
from agent_infra.projects.iteration_api import digest, document, identifier, items, number, text
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.research import ResearchService
from agent_infra.runs.control_api import SubmissionRequest
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.query import RunQueries


class IterationService:
    def __init__(
        self,
        store: LocalProjectStore,
        controller: LocalRunController,
        queries: RunQueries,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store, self.control, self.queries, self.clock = store, controller, queries, clock
        self.documents = IterationStore(store.database)
        self.research = ResearchService(store)

    def authorize(self, project: str, operation: str, value: dict[str, Any]) -> dict[str, Any]:
        obj = document(
            value,
            {
                "authorization",
                "tasks",
                "max_experiments",
                "total_seconds",
                "wall_seconds",
                "cpu",
                "memory_bytes",
                "stop_on_failure",
                "expected_revision",
                "expected_digest",
            },
            "iteration authorization",
        )
        identifier(operation)
        text(obj.get("authorization"), "authorization")
        maximum = obj.get("max_experiments")
        if type(maximum) is not int or not 1 <= maximum <= 100:
            raise ProjectError("max_experiments must be 1–100")
        for field in ("total_seconds", "wall_seconds"):
            number(obj.get(field), field, 1, 86400)
        number(obj.get("cpu"), "cpu", 0.01, 1024)
        memory = obj.get("memory_bytes")
        if type(memory) is not int or not 64 * 1024**2 <= memory <= 1024**4:
            raise ProjectError("memory_bytes must be an integer from 64 MiB to 1 TiB")
        if type(obj.get("stop_on_failure", True)) is not bool:
            raise ProjectError("stop_on_failure must be boolean")
        requests = [SubmissionRequest.from_dict(task) for task in items(obj.get("tasks"), "tasks")]
        key = digest({"project": project, "operation": operation})
        with self.store.writer():
            try:
                existing = self.documents.get(project, "workflow", key)
                if existing["request"] != obj:
                    raise ProjectConflict("authorization operation changed")
                return self._view(existing)
            except KeyError:
                pass
            context = self.research.context(project)
            if (context["research_revision"], context["digest"]) != (
                obj.get("expected_revision"),
                obj.get("expected_digest"),
            ) or context["unaccepted_changes"]:
                raise ProjectConflict("authorize the exact adopted research revision")
            tasks = {}
            for request in requests:
                prepared = self.control.prepare(request)
                resources = prepared.resources
                if (
                    prepared.lineage.get("project_id") != project
                    or prepared.lineage.get("research_revision") != context["research_revision"]
                    or resources.cpu_cores > obj["cpu"]
                    or resources.memory_bytes > memory
                    or resources.gpu.count
                    or request.timeout_seconds > obj["total_seconds"]
                ):
                    raise ProjectError("task exceeds project/revision/resource/time authorization")
                task_key = digest(asdict(request))
                tasks[task_key] = {
                    "request": asdict(request),
                    "lineage": prepared.lineage,
                    "image_id": prepared.request.resolved_image,
                    "resources": asdict(resources),
                }
            saved = {
                "workflow_id": key,
                "project_id": project,
                "request": obj,
                "tasks": tasks,
                "created_at": self.clock(),
                "deadline": self.clock() + obj["wall_seconds"],
                "state": "active",
                "actions": [],
                "reserved_seconds": 0.0,
                "cost": {
                    "observable": False,
                    "hard_limit_supported": False,
                    "note": "No billing feed; only count/time/resource limits are enforced.",
                },
            }
            self.documents.put(project, "workflow", key, saved)
            return self._view(saved)

    def _view(self, saved: dict[str, Any]) -> dict[str, Any]:
        value = dict(saved)
        value["actions"] = [dict(a) for a in saved["actions"]]
        for action in value["actions"]:
            # Recover the submit-receipt gap without executing any side effect on reads.
            run = self.control.store.lookup(action["submit_id"], action["request"])
            if run:
                action["run"] = run
        if value["state"] == "active":
            if self.clock() >= value["deadline"]:
                value.update(state="stopped", stop_reason="deadline")
            elif any(a.get("run", {}).get("state") != "finished" for a in value["actions"]):
                value["next_step"] = "wait_or_resume_pending_action"
            elif value["request"].get("stop_on_failure", True) and any(
                (a.get("run", {}).get("result") or {}).get("status")
                not in {"succeeded", "completed"}
                for a in value["actions"]
            ):
                value.update(state="stopped", stop_reason="failed_run")
            elif len(value["actions"]) >= value["request"]["max_experiments"]:
                value.update(state="stopped", stop_reason="experiment_budget")
            elif all(
                task["request"]["timeout_seconds"]
                > value["request"]["total_seconds"] - value["reserved_seconds"]
                for task in value["tasks"].values()
            ):
                value.update(state="stopped", stop_reason="execution_time_budget")
        return value

    def list(self, project: str) -> dict[str, Any]:
        self.research._project(project)
        return {"items": [self._view(value) for value in self.documents.list(project, "workflow")]}

    def status(self, project: str, workflow: str) -> dict[str, Any]:
        return self._view(self.documents.get(project, "workflow", workflow))

    def step(self, project: str, workflow: str, operation: str, task_key: str) -> dict[str, Any]:
        identifier(operation)
        with self.store.writer():
            saved = self.documents.get(project, "workflow", workflow)
            action = next((a for a in saved["actions"] if a["operation_id"] == operation), None)
            if action:
                if action["task_key"] != task_key:
                    raise ProjectConflict("iteration action already has a different task")
                run = self.control.store.lookup(action["submit_id"], action["request"])
                if run is not None:
                    return run
            current = self._view(saved)
            if current["state"] != "active":
                raise ProjectConflict(
                    f"iteration stopped: {current.get('stop_reason', current['state'])}"
                )
            if task_key not in saved["tasks"]:
                raise ProjectError("task is outside authorization; request a new user decision")
            if any(
                a is not action
                and (
                    (run := self.control.store.lookup(a["submit_id"], a["request"])) is None
                    or run["state"] != "finished"
                )
                for a in saved["actions"]
            ):
                raise ProjectConflict("an iteration action is pending or running")
            task = saved["tasks"][task_key]
            request = SubmissionRequest.from_dict(task["request"])
            if self.clock() + request.timeout_seconds > saved["deadline"]:
                raise ProjectConflict("insufficient remaining wall-clock budget")
            prepared = self.control.prepare(request)
            if (
                digest(prepared.lineage) != digest(task["lineage"])
                or prepared.request.resolved_image != task["image_id"]
                or digest(asdict(prepared.resources)) != digest(task["resources"])
            ):
                raise ProjectConflict("authorized task/image/resources changed")
            if action is None:
                if (
                    saved["reserved_seconds"] + request.timeout_seconds
                    > saved["request"]["total_seconds"]
                ):
                    raise ProjectConflict("execution time budget exhausted")
                action = {
                    "operation_id": operation,
                    "task_key": task_key,
                    "submit_id": "iteration:" + digest([workflow, operation]),
                    "request": task["request"],
                }
                saved["actions"].append(action)
                saved["reserved_seconds"] += request.timeout_seconds
                self.documents.put(project, "workflow", workflow, saved)
            # Intent and conservative budget charge precede execution. A crash after submit
            # is reconciled by the same controller operation key. No new action is invented.
            run = self.control.submit(
                action["submit_id"],
                request,
                expected_identity={
                    "lineage": task["lineage"],
                    "resources": task["resources"],
                    "image_id": task["image_id"],
                },
            )
            action["run_id"] = run["run_id"]
            self.documents.put(project, "workflow", workflow, saved)
            return run

    def stop(self, project: str, workflow: str, reason: str) -> dict[str, Any]:
        text(reason, "stop reason")
        with self.store.writer():
            saved = self.documents.get(project, "workflow", workflow)
            saved.update(state="stopped", stop_reason=reason)
            self.documents.put(project, "workflow", workflow, saved)
            for action in saved["actions"]:
                run = self.control.store.lookup(action["submit_id"], action["request"])
                if run and run["state"] != "finished":
                    self.control.cancel(run["run_id"])
            return self._view(saved)

    def read(
        self,
        project: str,
        workflow: str,
        run_id: str,
        artifact_id: str | None = None,
        member: str | None = None,
    ) -> dict[str, Any]:
        state = self.status(project, workflow)
        if run_id not in {a.get("run", {}).get("run_id") for a in state["actions"]}:
            raise ProjectError("Run is not part of this workflow")
        if artifact_id:
            return self.queries.artifact(run_id, artifact_id, member)
        return {"run": self.queries.status(run_id), "artifacts": self.queries.artifacts(run_id)}
