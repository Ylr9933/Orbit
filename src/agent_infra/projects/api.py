"""Public, side-effect-free project values and errors."""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID


class ProjectError(ValueError):
    code = "invalid_project"


class ProjectConflict(ProjectError):
    code = "project_conflict"


class ProjectNotFound(ProjectError):
    code = "project_not_found"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class InitializationStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    PROJECTION_PENDING = "projection_pending"


def require_text(value: str, name: str, limit: int = 100_000) -> None:
    if not isinstance(value, str) or not value.strip() or "\0" in value or len(value) > limit:
        raise ProjectError(f"{name} must be non-empty text (maximum {limit} characters)")


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    operation_id: str
    title: str
    original_goal: str
    workspace: str
    created_at: str
    updated_at: str
    schema_version: int = 1
    revision: int = 1
    status: ProjectStatus = ProjectStatus.DRAFT
    initialization: InitializationStatus = InitializationStatus.PENDING

    def __post_init__(self) -> None:
        try:
            UUID(self.project_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise ProjectError("project_id must be a UUID") from error
        require_text(self.operation_id, "operation_id", 200)
        require_text(self.title, "title", 200)
        require_text(self.original_goal, "goal")
        require_text(self.workspace, "workspace", 4096)
        if not Path(self.workspace).is_absolute() or ".." in Path(self.workspace).parts:
            raise ProjectError("workspace must be an absolute normalized path")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ProjectError("unsupported project schema_version")
        if type(self.revision) is not int or self.revision < 1:
            raise ProjectError("revision must be a positive integer")
        if not isinstance(self.status, ProjectStatus):
            raise ProjectError("invalid project status")
        if not isinstance(self.initialization, InitializationStatus):
            raise ProjectError("invalid initialization status")
        for value in (self.created_at, self.updated_at):
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError) as error:
                raise ProjectError("timestamps must be ISO 8601 with timezone") from error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "status": self.status.value,
            "initialization": self.initialization.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        if set(value) != set(cls.__dataclass_fields__):
            raise ProjectError("project fields do not match schema version 1")
        try:
            return cls(
                **(
                    value
                    | {
                        "status": ProjectStatus(value["status"]),
                        "initialization": InitializationStatus(value["initialization"]),
                    }
                )
            )
        except (TypeError, ValueError) as error:
            raise ProjectError(f"invalid project document: {error}") from error


@dataclass(frozen=True, slots=True)
class InitRequest:
    goal: str
    directory: Path | None = None
    name: str | None = None
    root: Path | None = None
    operation_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.goal, "goal")
        if self.name is not None:
            require_text(self.name, "name", 200)
        if self.operation_id is not None:
            require_text(self.operation_id, "operation_id", 200)


@dataclass(frozen=True, slots=True)
class InitPreview:
    project: Project
    directories: tuple[str, ...]
    files: dict[str, str]
    existing: bool = False
