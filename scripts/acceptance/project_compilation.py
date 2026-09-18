"""Exercise C01–C03 through an installed CLI; no model, Docker or training calls."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New scratch directory")
    parser.add_argument("--cli", default="agent-infra")
    args = parser.parse_args()
    samples = Path(__file__).resolve().parents[2] / "examples/research-compilation"
    root = args.output_dir.absolute()
    root.mkdir(parents=True, exist_ok=False)
    workspace, state = root / "project", root / "state"

    def call(*arguments: str, expected: int = 0) -> dict[str, Any]:
        result = subprocess.run(
            [args.cli, *arguments], cwd=root, capture_output=True, text=True, timeout=30
        )
        if result.returncode != expected:
            raise RuntimeError(f"CLI returned {result.returncode}: {result.stderr}")
        return dict(json.loads(result.stdout))

    def project(*arguments: str, expected: int = 0) -> dict[str, Any]:
        return call("project", *arguments, "--state-dir", str(state), expected=expected)

    identifier = project("init", str(workspace), "--goal", "Compare the mean and median")[
        "project"
    ]["project_id"]
    for name, target in {
        "compare.py": "code/src/compare.py",
        "values.csv": "data/raw/values.csv",
        "execution.yaml": "configs/experiments/pilot.yaml",
        "resources.yaml": "configs/resources/pilot.yaml",
    }.items():
        shutil.copyfile(samples / name, workspace / target)
    saved = project(
        "research",
        "save",
        identifier,
        "--file",
        str(samples / "draft.json"),
        "--expected-revision",
        "0",
        "--reason",
        "Compilation fixture",
    )["research"]
    command = (
        "compile",
        identifier,
        "--experiment",
        "pilot",
        "--revision",
        "1",
        "--execution",
        "configs/experiments/pilot.yaml",
    )
    assert project(*command, expected=1)["status"] == "needs_input"
    project(
        "research",
        "confirm",
        identifier,
        "--revision",
        "1",
        "--digest",
        saved["digest"],
        "--decision",
        "Adopt this synthetic fixture for compilation acceptance only",
    )
    first = project(*command)
    assert first["status"] == "compiled"
    assert project(*command)["compiled"] == first["compiled"]
    for action in ("validate", "view", "freeze"):
        call("task", action, first["manifest"])
    call("task", "prepare", first["manifest"], str(root / "solver-inputs"))
    assert not (root / "solver-inputs/control").exists()
    moved = root / "moved"
    workspace.rename(moved)
    project("rebind", identifier, "--directory", str(moved), "--expected-revision", "1")
    assert project(*command)["compiled"] == first["compiled"]
    doc = saved["document"]
    doc["plan"]["experiments"][0]["method"] += " Explain the influence of the outlier."
    proposal = root / "revised.json"
    proposal.write_text(json.dumps(doc), encoding="utf-8")
    second_draft = project(
        "research",
        "save",
        identifier,
        "--file",
        str(proposal),
        "--expected-revision",
        "1",
        "--reason",
        "Fixture correction",
    )["research"]
    project(
        "research",
        "confirm",
        identifier,
        "--revision",
        "2",
        "--digest",
        second_draft["digest"],
        "--decision",
        "Adopt corrected fixture for compilation",
    )
    second = project(
        "compile",
        identifier,
        "--experiment",
        "pilot",
        "--revision",
        "2",
        "--execution",
        "configs/experiments/pilot.yaml",
    )
    assert second["compiled"]["task"]["revision"] != first["compiled"]["task"]["revision"]
    old = first["compiled"]["task"]
    assert (
        project("resolve-task", old["task_id"], "--task-revision", old["revision"])["compiled"]
        == first["compiled"]
    )
    (moved / "data/raw/values.csv").unlink()
    assert (
        project(
            "compile",
            identifier,
            "--experiment",
            "pilot",
            "--revision",
            "2",
            "--execution",
            "configs/experiments/pilot.yaml",
            expected=1,
        )["status"]
        == "needs_input"
    )
    evidence = {
        "project_id": identifier,
        "first": first,
        "second": second,
        "model_calls": 0,
        "containers_started": 0,
        "passed": True,
    }
    (root / "acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "evidence": str(root / "acceptance.json")}))


if __name__ == "__main__":
    main()
