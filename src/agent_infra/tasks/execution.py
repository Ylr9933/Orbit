"""Trusted evaluation recipes; manifests select registered implementations, never commands."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_infra.environments.api import ProcessCommand


@dataclass(frozen=True, slots=True)
class EvaluationRecipe:
    evaluator_ref: str
    image: str
    scorer: ProcessCommand
    # Explicit material IDs mounted under /inputs/<id>, never the full task root.
    material_ids: tuple[str, ...]
    project_feedback: Callable[[dict[str, Any]], dict[str, Any]]
    # When present, executes untrusted submission WITHOUT private materials.
    submission_command: ProcessCommand | None = None
    prediction_paths: tuple[str, ...] = ()
    submission_image: str | None = None
    result_path: str = "result.json"
