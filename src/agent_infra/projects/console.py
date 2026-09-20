"""Non-destructive Web project view over the same services used by the CLI."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_infra.projects.api import InitializationStatus, InitRequest, ProjectError
from agent_infra.projects.compiler import CompilationService
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.research import ResearchService
from agent_infra.projects.service import ProjectService
from agent_infra.records.catalog import ProjectCatalog


class ProjectConsole:
    def __init__(
        self,
        store: LocalProjectStore,
        catalog: ProjectCatalog,
        *,
        run_references: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.store, self.catalog = store, catalog
        self.projects = ProjectService(store)
        self.research = ResearchService(store, run_references=run_references)
        self.compiler = CompilationService(store)

    def list_projects(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bindings, identities = self.catalog.bindings(), self.catalog.task_identities()
        current = {item["key"]: item for item in tasks if not item.get("error")}
        projects = {p.project_id: p for p in self.store.list_projects()}
        result = []
        for legacy in self.catalog.list_projects():
            project = projects.get(bindings.get(legacy["id"], ""))
            mappings = []
            for key in legacy["task_keys"]:
                identity = identities.get(key)
                observed = current.get(key)
                resolved = bool(
                    identity
                    and observed
                    and all(observed.get(field) == value for field, value in identity.items())
                )
                mappings.append({"key": key, "identity": identity, "resolved": resolved})
            result.append(
                legacy
                | {
                    "source": "legacy",
                    "workspace_project_id": project.project_id if project else None,
                    "workspace": project.workspace if project else None,
                    "binding_status": "bound" if project else "unbound",
                    "task_mappings": mappings,
                }
            )
        for project in projects.values():
            result.append(
                {
                    "id": project.project_id,
                    "name": project.title,
                    "goal": project.original_goal,
                    "status": project.status,
                    "revision": project.revision,
                    "milestones": [],
                    "run_ids": [],
                    "task_keys": [],
                    "source": "workspace",
                    "workspace_project_id": project.project_id,
                    "workspace": project.workspace,
                    "binding_status": project.initialization,
                    "task_mappings": [],
                }
            )
        return result

    def workspace_id(self, identifier: str) -> str:
        target = self.catalog.bindings().get(identifier, identifier)
        return self.store.get(target).project.project_id

    def detail(self, identifier: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        entry = next((p for p in self.list_projects(tasks) if p["id"] == identifier), None)
        if entry is None:
            raise KeyError(identifier)
        project = entry["workspace_project_id"]
        result: dict[str, Any] = {
            "project": entry,
            "research": None,
            "accepted": None,
            "compiled_tasks": [],
        }
        if project and self.store.get(project).project.initialization != InitializationStatus.READY:
            result["research_warning"] = "项目初始化或文档投影尚未完成；请使用 project recover 恢复"
            return result
        if project:
            context = self.research.context(project)
            accepted = context["accepted_revision"]
            result.update(
                research=context,
                accepted=self.research.show(project, revision=accepted) if accepted else None,
                compiled_tasks=self.compiler.list(project, limit=100)["compiled_tasks"],
            )
        return result

    def initialize(self, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"goal", "name", "directory", "operation_id"}:
            raise ProjectError("未知初始化字段")
        directory = body.get("directory")
        if not isinstance(directory, str) or not Path(directory).is_absolute():
            raise ProjectError("请输入服务器上的绝对工作区路径；其父目录必须已存在")
        if not isinstance(body.get("operation_id"), str) or not body["operation_id"].strip():
            raise ProjectError("初始化需要 operation_id，以便安全重试")
        return self.projects.initialize(
            InitRequest(
                goal=body.get("goal", ""),
                name=body.get("name"),
                directory=Path(directory),
                operation_id=body["operation_id"],
            )
        ).to_dict()

    def bind(self, identifier: str, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) != {"project_id"} or not isinstance(body["project_id"], str):
            raise ProjectError("请选择已有工作区项目")
        target = self.store.get(body["project_id"]).project
        self.catalog.bind(identifier, target.project_id)
        return {"project_id": target.project_id, "legacy_id": identifier}
