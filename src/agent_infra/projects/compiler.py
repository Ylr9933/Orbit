"""Coordinate deterministic Task compilation, publication and durable associations."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from agent_infra.contracts.files import content_digest
from agent_infra.projects import _filesystem as fs
from agent_infra.projects._compilation_store import CompilationStore
from agent_infra.projects._preparation import prepare_task_bundle
from agent_infra.projects.api import InitializationStatus, ProjectConflict, ProjectError
from agent_infra.projects.compilation_api import CompiledExperiment
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.research_api import ResearchRevision
from agent_infra.projects.service import ProjectService
from agent_infra.tasks import freeze_task, load_task


class CompilationService:
    def __init__(self, store: LocalProjectStore) -> None:
        self.store = store
        self.projects = ProjectService(store)
        self.links = CompilationStore(store.database)

    def compile(
        self,
        identifier: str,
        *,
        experiment_id: str,
        research_revision: int,
        execution: str | None = None,
        max_material_bytes: int = 1024**3,
    ) -> dict[str, Any]:
        if type(max_material_bytes) is not int or max_material_bytes <= 0:
            raise ProjectError("max_material_bytes must be a positive integer")
        with self.store.writer():
            project = self.projects.get(identifier)
            if project.initialization != InitializationStatus.READY:
                raise ProjectConflict("recover project initialization before compiling")
            with fs.directory(Path(project.workspace)) as root:
                self.projects._check_identity(root, ".", project)
            state = self.store.research_state(project.project_id)
            saved = self.store.research_revision(project.project_id, research_revision)
            experiments = saved.draft.to_dict()["plan"]["experiments"]
            experiment = next((e for e in experiments if e["id"] == experiment_id), None)
            if experiment is None:
                raise ProjectError("experiment does not exist in this research revision")
            issues = self._issues(saved, experiment, execution)
            if state["accepted"] is None or state["accepted"].revision != research_revision:
                issues.append(
                    {
                        "field": "research_revision",
                        "message": "Select the adopted revision; confirm the exact proposal first.",
                    }
                )
            if issues:
                return {"status": "needs_input", "issues": issues, "compiled": None}
            assert execution is not None
            bundle_root = self.store.root / "tasks"
            with fs.directory(bundle_root, create=True):
                pass
            with tempfile.TemporaryDirectory(prefix=".compile-", dir=bundle_root) as temp:
                stage = Path(temp) / "bundle"
                stage.mkdir(mode=0o700)
                try:
                    item = prepare_task_bundle(
                        project, saved, experiment, execution, stage, max_material_bytes
                    )
                except ProjectConflict:
                    raise
                except (OSError, ValueError) as error:
                    return {
                        "status": "needs_input",
                        "issues": [{"field": "materials_or_settings", "message": str(error)}],
                        "compiled": None,
                    }
                self._publish(stage, item)
                # If killed after publish, retry verifies identical content before re-registering.
                self.links.save(item)
                return {
                    "status": "compiled",
                    "issues": [],
                    "compiled": item.to_dict(),
                    "manifest": str(self._path(item) / "task.yaml"),
                    "execution_validated": False,
                }

    @staticmethod
    def _issues(
        saved: ResearchRevision, experiment: dict[str, Any], execution: str | None
    ) -> list[dict[str, str]]:
        doc = saved.draft.to_dict()
        issues = [{"field": "brief.unknowns", "message": text} for text in doc["brief"]["unknowns"]]
        if not doc["brief"]["question"]:
            issues.append({"field": "brief.question", "message": "Research question is missing."})
        for field in ("method", "outputs", "stopping_condition", "resource_request"):
            if not experiment[field]:
                issues.append({"field": field, "message": "Required before compilation."})
        for entry in experiment["inputs"]:
            if not entry["version"]:
                issues.append(
                    {"field": "inputs", "message": f"Data/code version is missing: {entry['path']}"}
                )
        if execution is None:
            issues.append(
                {
                    "field": "execution",
                    "message": "Provide a project-relative execution settings YAML.",
                }
            )
        return issues

    def _path(self, item: CompiledExperiment) -> Path:
        UUID(item.task.task_id)
        if not re.fullmatch(r"[0-9a-f]{64}", item.task.revision):
            raise ProjectError("invalid compiled task revision")
        return self.store.root / "tasks" / item.task.task_id / item.task.revision

    def _publish(self, stage: Path, item: CompiledExperiment) -> None:
        target = self._path(item)
        with fs.directory(target.parent, create=True) as parent:
            if fs.exists(parent, target.name):
                self._verify(item)
            else:
                # renameat2 supports an absolute source on the same filesystem.
                fs.publish(parent, str(stage), target.name)

    def _verify(self, item: CompiledExperiment) -> Path:
        root = self._path(item)
        with fs.directory(root):
            if content_digest(root) != item.bundle_digest:
                raise ProjectConflict(
                    "compiled bundle changed or has extra files; refusing to reuse"
                )
            task = load_task(root / "task.yaml")
            if (task.task_id, task.revision, freeze_task(task)) != (
                item.task.task_id,
                item.task.revision,
                item.task.snapshot,
            ):
                raise ProjectConflict("compiled task no longer matches its stored reference")
        return root / "task.yaml"

    def resolve(self, task_id: str, revision: str) -> dict[str, Any]:
        item = self.links.get(task_id, revision)
        return {
            "compiled": item.to_dict(),
            "manifest": str(self._verify(item)),
            "execution_validated": False,
        }

    def list(self, identifier: str, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        project = self.projects.get(identifier)
        return {
            "compiled_tasks": [
                i.to_dict() for i in self.links.list(project.project_id, limit=limit, offset=offset)
            ]
        }
