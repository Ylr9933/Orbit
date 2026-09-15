"""Apply traceable authoring suggestions without replacing supplied task facts."""

from __future__ import annotations

import json
from typing import Any

from agent_infra.tasks.api import FieldState, TaskDefinition
from agent_infra.tasks.manifest import SECTIONS, mapping, parse_task, task_document


def apply_research_proposal(
    task: TaskDefinition,
    changes: dict[str, Any],
    *,
    revision: str,
    explanation: str,
    evidence_ids: tuple[str, ...],
    origin: str = "agent_proposed",
) -> TaskDefinition:
    """Accept a structured proposal from any authoring Agent or user, never auto-generate data.

    Model invocation belongs to the authoring workflow. All suggestions retain their origin;
    applying a suggestion does not imply a resource grant or a user-approved scientific fact.
    """
    if task.mode != "research":
        raise ValueError("benchmark definitions cannot be completed with invented source fields")
    if not revision.strip() or revision == task.revision or not explanation.strip():
        raise ValueError("proposal requires a new revision and explanation")
    if origin not in {"user", "agent_proposed"}:
        raise ValueError("proposal origin must be user or agent_proposed")
    visible = {item.id for item in task.materials if "solver" in item.audiences}
    if not evidence_ids or not set(evidence_ids).issubset(visible):
        raise ValueError("proposal evidence must reference visible task materials")
    if not changes or set(changes) - set(SECTIONS):
        raise ValueError("proposals may only fill task sections, not rewrite instructions/data")
    document = task_document(task)
    for name, value in changes.items():
        if getattr(task, name).state not in {FieldState.UNSPECIFIED, FieldState.UNKNOWN}:
            raise ValueError(f"proposal cannot replace an established field: {name}")
        document[name] = mapping(value, name)
    extensions = json.loads(task.extensions_json)
    history = extensions.setdefault("agent_infra.authoring", [])
    if not isinstance(history, list):
        raise ValueError("invalid authoring history")
    history.append(
        {
            "origin": origin,
            "evidence_ids": list(evidence_ids),
            "explanation": explanation,
            "from_revision": task.revision,
            "revision": revision,
            "fields": sorted(changes),
        }
    )
    document["revision"] = revision
    document["extensions"] = extensions
    return parse_task(document, root=task.root)
