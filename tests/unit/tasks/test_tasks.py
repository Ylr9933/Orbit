"""Task preparation, visibility, source preservation and failure contracts."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml

from agent_infra.tasks import (
    apply_research_proposal,
    build_agent_view,
    build_evaluation_plan,
    create_research_draft,
    freeze_task,
    load_task,
    materialize_agent_view,
    review_draft,
    validate_resource_plan,
    validate_task,
    verify_evaluation_inputs,
    write_manifest,
)
from agent_infra.tasks.api import FieldState, TaskSection
from agent_infra.tasks.evaluation import EvaluatorRegistry, evaluate_text_example
from agent_infra.tasks.importers import import_asibench_workspace, import_researchclaw_workspace


@pytest.fixture
def task_file(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "instruction.md").write_text("Read the table and submit report.md.")
    (root / "data").mkdir()
    (root / "data" / "table.csv").write_text("x,y\n1,2\n")
    (root / "secret.txt").write_text("PRIVATE_CANARY_7281")
    draft = create_research_draft("test", root / "instruction.md", data=root / "data")
    write_manifest(draft, root / "task.yaml")
    payload = yaml.safe_load((root / "task.yaml").read_text())
    payload["materials"].append(
        {
            "id": "hidden-canary",
            "role": "evaluation_asset",
            "kind": "file",
            "source": "secret.txt",
            "description": "PRIVATE_CANARY_DESCRIPTION",
            "audiences": ["evaluator", "controller"],
            "provenance": {"origin": "user"},
        }
    )
    payload["outputs"] = {"state": "specified", "items": [{"path": "report.md", "required": True}]}
    payload["evaluation"] = {
        "state": "specified",
        "evaluator_ref": "registry:private-canary-eval",
        "audiences": ["evaluator", "controller"],
        "feedback": "after_submission",
    }
    (root / "task.yaml").write_text(yaml.safe_dump(payload))
    return root / "task.yaml"


def test_private_references_and_files_never_enter_view(task_file: Path, tmp_path: Path) -> None:
    task = load_task(task_file)
    view = build_agent_view(task)
    encoded = json.dumps(asdict(view))
    assert "canary" not in encoded.lower()
    assert "secret.txt" not in encoded
    assert str(task.root) not in encoded
    destination = tmp_path / "solver"
    assert materialize_agent_view(task, freeze_task(task), destination) == view
    assert (destination / "data" / "table.csv").read_text() == "x,y\n1,2\n"
    assert not (destination / "secret.txt").exists()
    assert not (destination / "task.yaml").exists()


def test_changed_inputs_invalidate_snapshot(task_file: Path, tmp_path: Path) -> None:
    task = load_task(task_file)
    snapshot = freeze_task(task)
    (task.root / "data" / "table.csv").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        materialize_agent_view(task, snapshot, tmp_path / "solver")


def test_private_directory_overlap_is_rejected(task_file: Path) -> None:
    task = load_task(task_file)
    public = replace(task.materials[1], source="data")
    (task.root / "data" / "secret.txt").write_text("hidden")
    hidden = replace(task.materials[-1], source="data/secret.txt")
    task = replace(task, materials=(task.materials[0], public, hidden))
    assert "visibility_overlap" in {issue.code for issue in validate_task(task)}
    with pytest.raises(ValueError, match="controller diagnostics"):
        build_agent_view(task)


def test_symlink_to_private_file_is_rejected(task_file: Path) -> None:
    task = load_task(task_file)
    (task.root / "data" / "link").symlink_to(task.root / "secret.txt")
    assert validate_task(task)
    with pytest.raises(ValueError):
        freeze_task(task)


@pytest.mark.parametrize(
    "replacement",
    [
        "schema_version: true",
        "schema_version: 2",
        "schema_version: 1\nschema_version: 1",
        "schema_version: &x 1\nrevision: *x",
        "schema_version: 1\nunknown_field: yes",
    ],
)
def test_malformed_manifest_is_rejected(tmp_path: Path, replacement: str) -> None:
    path = tmp_path / "task.yaml"
    path.write_text(replacement)
    with pytest.raises(ValueError):
        load_task(path)


def test_round_trip_and_missing_state(task_file: Path) -> None:
    task = load_task(task_file)
    assert task.tools.state is FieldState.UNSPECIFIED
    write_manifest(task, task.root / "copy.yaml")
    assert load_task(task.root / "copy.yaml") == task
    assert review_draft(task).status == "ready"
    with pytest.raises(FileExistsError):
        write_manifest(task, task.root / "copy.yaml")


def test_no_invented_data_or_evaluator(tmp_path: Path) -> None:
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Investigate this scientific question")
    draft = create_research_draft("question", instruction)
    assert len(draft.materials) == 1
    assert draft.evaluation.state is FieldState.UNSPECIFIED
    assert review_draft(draft).status == "needs_input"
    assert review_draft(draft).issues[0].code == "needs_output"


def test_resource_choice_preserves_native_intent(task_file: Path, tmp_path: Path) -> None:
    task = replace(
        load_task(task_file),
        resource_intent=TaskSection(
            FieldState.SPECIFIED,
            json.dumps({"constraints": {"cpu_min": 2, "cpu_max": 3}}),
        ),
    )
    request = tmp_path / "resources.yaml"
    request.write_text("version: 1\nrequest_id: r1\nresources:\n  cpu: 3\n  memory: 1GiB\n")
    original = task.resource_intent
    assert validate_resource_plan(task, request).cpu_cores == 3
    request.write_text(request.read_text().replace("cpu: 3", "cpu: 4"))
    with pytest.raises(ValueError, match="cpu_max"):
        validate_resource_plan(task, request)
    assert task.resource_intent == original


def test_native_workspace_import_preserves_bytes_and_missing_fields(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("Original native template output\n")
    (tmp_path / "related_work").mkdir()
    (tmp_path / "related_work" / "reference.txt").write_text("reference")
    (tmp_path / "checklist.txt").write_text("must not import")
    task = import_researchclaw_workspace(tmp_path, native_id="sample", source_revision="native-rev")
    assert task.resource_intent.state is FieldState.UNSPECIFIED
    assert task.evaluation.state is FieldState.UNSPECIFIED
    assert {item.role for item in task.materials} == {"instruction", "reference"}
    assert (tmp_path / "INSTRUCTIONS.md").read_text() == "Original native template output\n"
    assert "checklist" not in json.dumps(asdict(build_agent_view(task)))


def test_evaluation_detects_submission_mutation(task_file: Path, tmp_path: Path) -> None:
    task = load_task(task_file)
    submission = tmp_path / "submission"
    submission.mkdir()
    (submission / "report.md").write_text("result")
    plan = build_evaluation_plan(task, submission)
    verify_evaluation_inputs(task, plan)
    (submission / "report.md").write_text("changed result")
    with pytest.raises(ValueError, match="changed"):
        verify_evaluation_inputs(task, plan)


def test_authoring_proposals_keep_origin_and_existing_facts(tmp_path: Path) -> None:
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Research this question")
    draft = create_research_draft("research", instruction)
    updated = apply_research_proposal(
        draft,
        {"outputs": {"state": "specified", "items": [{"path": "report.md", "required": True}]}},
        revision="draft-2",
        explanation="Proposed report location",
        evidence_ids=("instruction",),
    )
    assert updated.materials == draft.materials
    assert updated.resource_intent == draft.resource_intent
    assert "agent_proposed" in updated.extensions_json
    assert draft.outputs.state is FieldState.UNSPECIFIED
    with pytest.raises(ValueError, match="established"):
        apply_research_proposal(
            updated,
            {"outputs": {"state": "none"}},
            revision="draft-3",
            explanation="replace",
            evidence_ids=("instruction",),
        )
    with pytest.raises(ValueError, match="visible"):
        apply_research_proposal(
            draft,
            {"outputs": {"state": "none"}},
            revision="draft-2",
            explanation="hidden hint",
            evidence_ids=("private",),
        )


@pytest.mark.parametrize("source", ["../secret.txt", "/etc/passwd", "data/../../secret.txt"])
def test_traversal_sources_rejected(task_file: Path, source: str) -> None:
    payload = yaml.safe_load(task_file.read_text())
    payload["materials"][0]["source"] = source
    task_file.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="relative"):
        load_task(task_file)


def test_overlapping_targets_rejected(task_file: Path) -> None:
    task = load_task(task_file)
    task = replace(
        task,
        materials=(replace(task.materials[0], target="data/instruction.md"), *task.materials[1:]),
    )
    assert "target_overlap" in {issue.code for issue in validate_task(task)}


def test_asibench_import_only_exposes_selected_prompt(tmp_path: Path) -> None:
    for level in ("b1", "b2", "b3", "b4"):
        (tmp_path / f"prompt_{level}.md").write_text(f"native {level} instruction")
    (tmp_path / "input.txt").write_text("input")
    task = import_asibench_workspace(
        tmp_path,
        native_id="test",
        source_revision="revision",
        level="b3",
        input_paths=("input.txt",),
    )
    view = build_agent_view(task)
    assert view.instructions == ("prompt_b3.md",)
    assert len(view.materials) == 2
    assert task.tools.state is FieldState.UNSPECIFIED
    with pytest.raises(ValueError, match="benchmark"):
        apply_research_proposal(
            task,
            {"tools": {"state": "none"}},
            revision="changed",
            explanation="invented",
            evidence_ids=("instruction",),
        )


def test_example_evaluation_distinguishes_wrong_submission_and_execution_error(
    tmp_path: Path,
) -> None:
    task = load_task(Path("examples/task-packages/file-result/task.yaml"))
    submission = tmp_path / "submission"
    submission.mkdir()
    registry = EvaluatorRegistry({"example:text-exact-v1": evaluate_text_example})
    result = registry.evaluate(task, build_evaluation_plan(task, submission))
    assert result.status == "succeeded"
    assert json.loads(result.native_result_json or "null") == {"passed": False}
    (submission / "result.txt").write_text("HELLO TASK\n")
    result = registry.evaluate(task, build_evaluation_plan(task, submission))
    assert json.loads(result.native_result_json or "null") == {"passed": True}

    def broken(task: object, plan: object) -> str:
        raise RuntimeError("private scorer details")

    failure = EvaluatorRegistry({"example:text-exact-v1": broken}).evaluate(
        task,
        build_evaluation_plan(task, submission),
    )
    assert failure.status == "failed"
    assert "private scorer" not in repr(failure)


def test_invalid_section_not_silently_accepted(task_file: Path) -> None:
    payload = yaml.safe_load(task_file.read_text())
    payload["resource_intent"] = {"state": "specified", "constraints": {"cpus_min": 2}}
    task_file.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="unknown"):
        load_task(task_file)
