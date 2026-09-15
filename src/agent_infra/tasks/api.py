"""Immutable task contracts. Full definitions are controller-only objects."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FieldState(StrEnum):
    UNSPECIFIED = "unspecified"
    NONE = "none"
    UNKNOWN = "unknown"
    SPECIFIED = "specified"


@dataclass(frozen=True, slots=True)
class Provenance:
    origin: str
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class TaskSection:
    state: FieldState
    # Canonical JSON preserves native extensions without exposing mutable dictionaries.
    value_json: str = "{}"


@dataclass(frozen=True, slots=True)
class Material:
    id: str
    role: str
    kind: str
    source: str
    description: str
    audiences: tuple[str, ...]
    target: str | None
    access: str
    availability: str
    provenance: Provenance
    media_type: str | None = None
    digest: str | None = None


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    task_id: str
    revision: str
    mode: str
    root: Path
    source_json: str
    instructions: tuple[str, ...]
    materials: tuple[Material, ...]
    user_context: tuple[str, ...]
    tools: TaskSection
    resource_intent: TaskSection
    environment: TaskSection
    outputs: TaskSection
    evaluation: TaskSection
    execution_policy: TaskSection
    extensions_json: str


@dataclass(frozen=True, slots=True)
class TaskIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class VisibleMaterial:
    id: str
    role: str
    kind: str
    path: str
    description: str
    access: str
    media_type: str | None


@dataclass(frozen=True, slots=True)
class ToolRequirement:
    tool_id: str
    version: str
    required: bool
    transport: str
    scope: str


@dataclass(frozen=True, slots=True)
class AgentTaskView:
    task_id: str
    revision: str
    instructions: tuple[str, ...]
    user_context: tuple[str, ...]
    materials: tuple[VisibleMaterial, ...]
    # Only explicitly public output requirements are projected.
    outputs: TaskSection
    tools: tuple[ToolRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    definition_digest: str
    material_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class DraftReview:
    status: str
    issues: tuple[TaskIssue, ...]


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    evaluator_ref: str
    task_snapshot: TaskSnapshot
    submission_root: Path
    submission_digest: str
    private_material_ids: tuple[str, ...]
    feedback: str
