"""Deterministic package-resource rendering; no model or filesystem writes."""

import json
from dataclasses import replace
from importlib.resources import files
from string import Template

import yaml

from agent_infra.projects.api import InitializationStatus, Project

DIRECTORIES = (
    "docs/decisions",
    "docs/analyses",
    "docs/reports",
    "code/src",
    "code/tests",
    "configs/experiments",
    "configs/resources",
    "configs/environments",
    "data/manifests",
    "data/raw",
    "data/processed",
    "runs",
    "artifacts",
    ".agent-infra/locks",
)


def manifest(project: Project) -> str:
    return yaml.safe_dump(
        replace(project, initialization=InitializationStatus.READY).to_dict(),
        allow_unicode=True,
        sort_keys=False,
    )


def render(project: Project) -> dict[str, str]:
    templates: dict[str, str] = json.loads(
        files("agent_infra.projects").joinpath("templates/workspace.json").read_text("utf-8")
    )
    context = {
        "title": project.title,
        "goal": project.original_goal,
        "project_id": project.project_id,
    }
    result = {name: Template(text).substitute(context) for name, text in templates.items()}
    result["project.yaml"] = manifest(project)
    result[".agent-infra/project.json"] = (
        json.dumps(
            {
                "project_id": project.project_id,
                "operation_id": project.operation_id,
                "template_version": 1,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    return result
