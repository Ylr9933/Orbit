"""Compilation values: durable lineage, portable task identity, local resolution."""

from dataclasses import asdict, dataclass
from typing import Any

from agent_infra.tasks import TaskReference, TaskSnapshot


@dataclass(frozen=True, slots=True)
class CompiledExperiment:
    project_id: str
    experiment_id: str
    research_revision: int
    research_digest: str
    task: TaskReference
    bundle_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompiledExperiment":
        reference = data["task"]
        snapshot = reference["snapshot"]
        return cls(
            data["project_id"],
            data["experiment_id"],
            data["research_revision"],
            data["research_digest"],
            TaskReference(
                reference["task_id"],
                reference["revision"],
                TaskSnapshot(
                    snapshot["definition_digest"],
                    tuple(tuple(pair) for pair in snapshot["material_digests"]),
                ),
            ),
            data["bundle_digest"],
        )
