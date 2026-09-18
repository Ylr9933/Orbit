"""Thin CLI composition for compilation, task lookup and workspace rebinding."""

from pathlib import Path
from typing import Any

from agent_infra.projects.compiler import CompilationService
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.relocation import rebind_project


def compilation_action(
    store: LocalProjectStore, action: str, options: dict[str, str]
) -> dict[str, Any]:
    service = CompilationService(store)
    if action == "compile":
        return service.compile(
            options["identifier"],
            experiment_id=options["experiment"],
            research_revision=int(options["revision"]),
            execution=options.get("execution"),
            max_material_bytes=int(options["max_material_bytes"]),
        )
    if action == "compiled-tasks":
        return service.list(
            options["identifier"], limit=int(options["limit"]), offset=int(options["offset"])
        )
    if action == "resolve-task":
        return service.resolve(options["task_id"], options["task_revision"])
    if action == "rebind":
        return {
            "project": rebind_project(
                store,
                options["identifier"],
                Path(options["directory"]),
                expected_revision=int(options["expected_revision"]),
            ).to_dict()
        }
    raise ValueError(f"unknown compilation action: {action}")
