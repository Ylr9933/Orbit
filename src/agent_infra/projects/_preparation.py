"""Prepare one selected experiment through public Tasks and Resources contracts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from agent_infra.contracts.files import content_digest, relative_path, resolve_material
from agent_infra.projects import _filesystem as fs
from agent_infra.projects._materials import CopyBudget, copy_material
from agent_infra.projects._task_rendering import instruction, manifest_document, material
from agent_infra.projects.api import Project, ProjectConflict, ProjectError
from agent_infra.projects.compilation_api import CompiledExperiment
from agent_infra.projects.research_api import ResearchRevision
from agent_infra.resources import load_resource_request
from agent_infra.tasks import (
    TaskReference,
    build_agent_view,
    freeze_task,
    load_execution_settings,
    load_task,
    review_draft,
    validate_resource_plan,
)


def prepare_task_bundle(
    project: Project,
    saved: ResearchRevision,
    experiment: dict[str, Any],
    execution: str,
    stage: Path,
    max_bytes: int,
) -> CompiledExperiment:
    workspace = Path(project.workspace)
    budget = CopyBudget(max_bytes)
    # Destinations are disjoint; settings and resources are controller-only materials.
    sources = [
        (e["path"], f"inputs/{n}", e["path"], f"input-{n}", e["description"] or e["path"])
        for n, e in enumerate(experiment["inputs"])
    ]
    sources.extend(
        [
            (
                execution,
                "control/execution.yaml",
                None,
                "execution-settings",
                "Execution settings",
            ),
            (
                experiment["resource_request"],
                "control/resources.yaml",
                None,
                "resource-request",
                "Resource request",
            ),
        ]
    )
    targets = [relative_path(s[2]) for s in sources if s[2]]
    reserved = relative_path(".agent-infra")
    for index, target in enumerate(targets):
        if target.is_relative_to(reserved) or reserved.is_relative_to(target):
            raise ProjectError("input target overlaps reserved .agent-infra directory")
        if any(target.is_relative_to(old) or old.is_relative_to(target) for old in targets[:index]):
            raise ProjectError("selected input paths overlap; select each material once")
    outputs = [relative_path(p) for p in experiment["outputs"]]
    for index, output in enumerate(outputs):
        if any(
            output.is_relative_to(t) or t.is_relative_to(output)
            for t in [reserved, *targets, *outputs[:index]]
        ):
            raise ProjectError("output paths overlap inputs, each other or reserved paths")
    materials = []
    fingerprints = []
    for source, destination, target_path, identifier, description in sources:
        path = resolve_material(workspace, source)
        copy_material(workspace, source, stage / destination, budget)
        copied = material(stage, destination, target_path, identifier, description)
        before = content_digest(path)
        if copied["digest"] != before:
            raise ProjectConflict("material changed during preparation")
        fingerprints.append((source, before))
        materials.append(copied)
    settings = load_execution_settings(stage / "control/execution.yaml")
    if settings.get("evaluation") != {"state": "none"}:
        raise ProjectError(
            "research compilation requires explicit evaluation: {state: none}; "
            "native benchmarks use their existing adapters"
        )
    if settings.get("tools", {}).get("state") not in {"none", "specified"}:
        raise ProjectError("declare extra tools explicitly, or tools: {state: none}")
    environment = settings.get("environment", {})
    if (
        environment.get("state") != "specified"
        or not isinstance(environment.get("image"), str)
        or not environment["image"].strip()
    ):
        raise ProjectError("execution environment requires an explicit existing image reference")
    resources = load_resource_request(stage / "control/resources.yaml")
    with fs.directory(stage) as root:
        fs.write_file(root, "instruction.md", instruction(project, saved, experiment).encode())
    materials.insert(
        0,
        material(
            stage,
            "instruction.md",
            ".agent-infra/instruction.md",
            "instruction",
            "Selected experiment instructions",
        ),
    )
    document = manifest_document(
        project, saved, experiment, materials, settings, resources, execution
    )
    with fs.directory(stage) as root:
        fs.write_file(
            root,
            "task.yaml",
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode(),
        )
    task = load_task(stage / "task.yaml")
    review = review_draft(task)
    if review.issues:
        raise ProjectError(json.dumps(asdict(review), ensure_ascii=False))
    build_agent_view(task)
    snapshot = freeze_task(task)
    validate_resource_plan(task, stage / "control/resources.yaml")
    for source, before in fingerprints:
        if content_digest(resolve_material(workspace, source)) != before:
            raise ProjectConflict(
                "project materials changed during compilation; retry after writers finish"
            )
    return CompiledExperiment(
        project.project_id,
        experiment["id"],
        saved.revision,
        saved.draft.digest,
        TaskReference(task.task_id, task.revision, snapshot),
        content_digest(stage),
    )
