"""Pure conversion of selected research content to the existing Task manifest schema."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from agent_infra.contracts.files import content_digest
from agent_infra.projects.api import Project
from agent_infra.projects.research_api import ResearchRevision
from agent_infra.resources import ResourceRequest


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instruction(project: Project, saved: ResearchRevision, experiment: dict[str, Any]) -> str:
    doc = saved.draft.to_dict()
    brief = doc["brief"]
    parts = [
        "# Research experiment",
        "## Original goal",
        project.original_goal,
        "## Research question",
        brief["question"],
        "## Background",
        brief["background"],
        "## Constraints",
        "\n".join(f"- {c}" for c in brief["constraints"]),
        "## Success criteria",
        brief["success_criteria"],
    ]
    for key in (
        "id",
        "title",
        "hypothesis",
        "method",
        "controls",
        "variables",
        "stopping_condition",
    ):
        parts.extend(["## " + key.replace("_", " ").capitalize(), experiment[key]])
    for key in ("inputs", "outputs", "metrics"):
        parts.extend(
            ["## " + key.capitalize(), json.dumps(experiment[key], ensure_ascii=False, indent=2)]
        )
    parts.extend(
        [
            "## Workspace",
            "Input and output paths are relative to the solver workspace. "
            "Only selected inputs are provided. No automatic evaluation is configured.",
        ]
    )
    return "\n\n".join(parts) + "\n"


def material(
    root: Path, source: str, target: str | None, identifier: str, description: str
) -> dict[str, Any]:
    path = root / source
    return {
        "id": identifier,
        "role": "instruction" if identifier == "instruction" else "input",
        "kind": "directory" if path.is_dir() else "file",
        "source": source,
        "description": description,
        "audiences": ["solver", "controller"] if target else ["controller"],
        "target": target,
        "access": "read_only",
        "availability": "present",
        "provenance": {"origin": "adapter"},
        "digest": content_digest(path),
    }


def manifest_document(
    project: Project,
    saved: ResearchRevision,
    experiment: dict[str, Any],
    materials: list[dict[str, Any]],
    settings: dict[str, Any],
    resources: ResourceRequest,
    execution_path: str,
) -> dict[str, Any]:
    source = {
        "kind": "project_experiment",
        "project_id": project.project_id,
        "experiment_id": experiment["id"],
        "research_revision": saved.revision,
        "research_digest": saved.draft.digest,
    }
    task_id = str(
        uuid5(NAMESPACE_URL, f"agent-infra/experiment/{project.project_id}/{experiment['id']}")
    )
    document: dict[str, Any] = {
        "schema_version": 1,
        "task_id": task_id,
        "mode": "research",
        "source": source,
        "instructions": ["instruction"],
        "materials": materials,
        "outputs": {
            "state": "specified",
            "items": [{"path": path, "required": True} for path in experiment["outputs"]],
        },
        "resource_intent": {
            "state": "specified",
            "constraints": {
                "cpu_min": resources.cpu_cores,
                "cpu_max": resources.cpu_cores,
                "memory_min": f"{resources.memory_bytes}B",
                "memory_max": f"{resources.memory_bytes}B",
                "gpu_min": resources.gpu.count,
                "gpu_max": resources.gpu.count,
            },
        },
        "extensions": {
            "agent_infra_compilation": {
                "version": 1,
                "resource_request": "control/resources.yaml",
                "execution_settings_source": execution_path,
                "inputs": experiment["inputs"],
                "metrics": experiment["metrics"],
                "stopping_condition": experiment["stopping_condition"],
            }
        },
        **settings,
    }
    # The revision hashes the content without itself; no timestamps or absolute paths.
    document["revision"] = digest(document)
    return document
