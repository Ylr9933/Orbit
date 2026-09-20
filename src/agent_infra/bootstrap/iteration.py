"""Compose Projects analysis/workflows with the existing controller and public Records reads."""

from pathlib import Path
from typing import Any

from agent_infra.projects.analysis import AnalysisService
from agent_infra.projects.iteration import IterationService
from agent_infra.projects.local import LocalProjectStore
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.query import RunQueries


class StudyActions:
    def __init__(self, state: Path, controller: LocalRunController, queries: RunQueries) -> None:
        store = LocalProjectStore(state / "projects")
        self.analysis = AnalysisService(store, queries)
        self.iteration = IterationService(store, controller, queries)

    def call(
        self, project: str, action: str, options: dict[str, Any], operation: str | None
    ) -> dict[str, Any]:
        if action == "study_analysis_save":
            return self.analysis.save(project, str(operation or ""), options["document"])
        if action == "study_decide":
            return self.analysis.decide(project, str(operation or ""), options["document"])
        if action == "study_analyses":
            return self.analysis.list(project, "analysis")
        if action == "study_decisions":
            return self.analysis.list(project, "decision")
        if action == "study_authorize":
            return self.iteration.authorize(project, str(operation or ""), options["document"])
        if action == "study_workflows":
            return self.iteration.list(project)
        if action == "study_status":
            return self.iteration.status(project, options["workflow_id"])
        if action == "study_step":
            return self.iteration.step(
                project, options["workflow_id"], str(operation or ""), options["task_key"]
            )
        if action == "study_stop":
            return self.iteration.stop(project, options["workflow_id"], options["reason"])
        if action == "study_read":
            return self.iteration.read(
                project,
                options["workflow_id"],
                options["run_id"],
                options.get("artifact_id"),
                options.get("member"),
            )
        raise ValueError("unknown study action")

    def planner_call(
        self, project: str, workflow: str, action: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        if action == "context":
            return {
                "research": self.analysis.research.context(project),
                "workflow": self.iteration.status(project, workflow),
            }
        if action == "analysis":
            for reference in options["document"].get("results", []):
                self.iteration.read(project, workflow, reference["run_id"])
            return self.analysis.save(project, options["operation_id"], options["document"])
        if action not in {"status", "step", "read"}:
            raise ValueError("Planner permits only context, status, step, read and analysis")
        # Binding cannot be overridden by any field supplied by the container.
        return self.call(
            project,
            "study_" + action,
            options | {"workflow_id": workflow},
            options.get("operation_id"),
        )
