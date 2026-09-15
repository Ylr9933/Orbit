"""Import native-prepared workspaces without rewriting instructions or source protocols."""

from pathlib import Path
from typing import Any

from agent_infra.tasks.api import TaskDefinition
from agent_infra.tasks.manifest import content_digest, parse_task, resolve_material


def import_native_workspace(
    root: Path,
    *,
    benchmark: str,
    native_id: str,
    source_revision: str,
    instruction: str,
    inputs: tuple[str, ...] = (),
    references: tuple[str, ...] = (),
    variant: str | None = None,
) -> TaskDefinition:
    """Explicit allowlist import. No inference of evaluators, outputs, budgets or tools.

    Callers must provide a workspace already prepared with the native loader. This is
    an indexed import, not a certification of native evaluator or runtime equivalence.
    """
    materials: list[dict[str, Any]] = []
    for role, paths in (
        ("instruction", (instruction,)),
        ("data", inputs),
        ("reference", references),
    ):
        for index, source in enumerate(paths):
            path = resolve_material(root.resolve(), source)
            identifier = "instruction" if role == "instruction" else f"{role}-{index}"
            materials.append(
                {
                    "id": identifier,
                    "role": role,
                    "kind": "directory" if path.is_dir() else "file",
                    "source": source,
                    "description": f"Native {role} material",
                    "audiences": ["solver", "evaluator", "controller"],
                    "target": source,
                    "access": "writable_copy",
                    "availability": "present",
                    "provenance": {"origin": "native", "evidence": source_revision},
                    "digest": content_digest(path),
                }
            )
    return parse_task(
        {
            "schema_version": 1,
            "task_id": f"{benchmark}:{native_id}",
            "revision": source_revision,
            "mode": "benchmark",
            "source": {
                "kind": "benchmark",
                "benchmark": benchmark,
                "native_id": native_id,
                "revision": source_revision,
                "variant": variant,
                "adapter_version": "1",
            },
            "instructions": ["instruction"],
            "materials": materials,
            "extensions": {"agent_infra.import": {"compatibility": "indexed_only"}},
        },
        root=root,
    )


def import_researchclaw_workspace(
    root: Path,
    *,
    native_id: str,
    source_revision: str,
) -> TaskDefinition:
    """Index an existing native TaskRunner workspace; never reconstruct its prompt."""
    return import_native_workspace(
        root,
        benchmark="researchclawbench",
        native_id=native_id,
        source_revision=source_revision,
        instruction="INSTRUCTIONS.md",
        inputs=("data",) if (root / "data").exists() else (),
        references=("related_work",) if (root / "related_work").exists() else (),
    )


def import_asibench_workspace(
    root: Path,
    *,
    native_id: str,
    source_revision: str,
    level: str,
    input_paths: tuple[str, ...],
) -> TaskDefinition:
    """Index a selected prompt and explicitly declared, native-generated inputs.

    Never include the task root, other prompt levels, generator or scoring configuration.
    The caller must stage the native prompt under its original prompt_bN.md name.
    """
    if level not in {"b1", "b2", "b3", "b4"}:
        raise ValueError("ASI-Bench level must be b1, b2, b3 or b4")
    return import_native_workspace(
        root,
        benchmark="asibench",
        native_id=native_id,
        source_revision=source_revision,
        instruction=f"prompt_{level}.md",
        inputs=input_paths,
        variant=level,
    )
