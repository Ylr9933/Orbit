"""Adapt research CLI values to existing project services."""

from pathlib import Path
from typing import Any

from agent_infra.projects import ProjectError
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.research import ResearchService, load_research_draft
from agent_infra.runs.control_store import RunControlStore


def research_action(
    store: LocalProjectStore, action: str, options: dict[str, str]
) -> dict[str, Any]:
    service = ResearchService(store)
    identifier = options["identifier"]
    revision = int(options["revision"]) if "revision" in options else None
    if action == "save":
        draft = load_research_draft(Path(options["file"]))
        return service.save(
            identifier,
            draft,
            expected_revision=int(options["expected_revision"]),
            reason=options["reason"],
        )
    if action == "show":
        return service.show(identifier, revision)
    if action == "history":
        return {
            "history": service.history(
                identifier,
                limit=int(options.get("limit", "20")),
                before=int(options["before"]) if "before" in options else None,
            )
        }
    if action == "diff":
        return service.diff(identifier, int(options["from_revision"]), int(options["to_revision"]))
    if action == "confirm":
        return {
            "confirmation": service.confirm(
                identifier,
                revision=int(options["revision"]),
                digest=options["digest"],
                decision=options["decision"],
            )
        }
    if action == "context":
        result = service.context(identifier)
        root = store.root.parent / "controller"
        result["run_references"] = (
            RunControlStore(root).list_runs(project_id=result["project"]["project_id"], limit=20)
            if (root / "control.sqlite3").is_file()
            else []
        )
        result["execution_links_supported"] = True
        return result
    if action == "check":
        return service.check(identifier, revision)
    if action == "export":
        return {"projection": service.export(identifier)}
    if action == "import-notes":
        return service.import_notes(
            identifier,
            Path(options["file"]),
            section=options["section"],
            expected_revision=int(options["expected_revision"]),
            reason=options["reason"],
        )
    if action == "skill":
        return service.skill(identifier, install=options.get("install") == "True")
    raise ProjectError(f"unknown research action: {action}")
