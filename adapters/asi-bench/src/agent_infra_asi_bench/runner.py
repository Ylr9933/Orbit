"""Run one pinned ASI-Bench public attempt and score its materialized output."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

from ai4sci_bench.benchflow import score_manifest_file

from agent_infra.contracts.files import content_digest

from .request import Request


def _single_result(root: Path) -> Path:
    results = [
        path
        for path in root.rglob("*.json")
        if path.name not in {"run_metadata.json", "benchflow_manifest.json", "benchflow_score.json"}
        and path.parent.name != "batch_records"
    ]
    matches = []
    for path in results:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "agent_output" in data and "instance_id" in data:
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(f"expected one native result, found {len(matches)}")
    return matches[0]


def run(request: Request) -> int:
    root = Path.cwd()
    instance = Path(request.instance_dir).resolve()
    tasks = Path(request.tasks_dir).resolve()
    if content_digest(instance) != request.instance_digest:
        raise ValueError("instance snapshot changed after planning")
    task_dir = tasks / Path(*request.task_id.split("."))
    if content_digest(task_dir) != request.tasks_digest:
        raise ValueError("task/scorer snapshot changed after planning")
    scorer_policy = tasks.parent / "config" / "public_scorers.json"
    if content_digest(scorer_policy) != request.scorer_policy_digest:
        raise ValueError("public scorer policy changed after planning")

    native = root / "native"
    native.mkdir()
    agent_command = " ".join(
        (
            shlex.quote(sys.executable),
            "-m",
            "agent_infra_asi_bench.fixture_agent",
            "--workspace",
            "{workspace}",
        )
    )
    command = [
        sys.executable,
        "-m",
        "ai4sci_bench.cli",
        "run",
        "--tasks",
        request.task_id,
        "--prompt-levels",
        request.prompt_level,
        "--instances-dir",
        str(instance.parent),
        "--tasks-dir",
        str(tasks),
        "--agent-cmd",
        agent_command,
        "--sandbox",
        "none",
        "--parallel",
        "1",
        "--retries",
        "1",
        "--timeout",
        str(request.timeout_seconds),
        "--output-dir",
        str(native),
    ]
    completed = subprocess.run(command, check=False)
    result_path = _single_result(native)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("task_id") != request.task_id or result.get("instance_id") != request.instance_id:
        raise ValueError("native runner changed task or instance identity")
    if result.get("prompt_level") != request.prompt_level:
        raise ValueError("native runner changed prompt level")
    persisted = result.get("agent_output", {}).get("persisted_outputs", {}).get("dir")
    if not persisted:
        raise ValueError("native runner did not persist the prediction")
    prediction = (result_path.parent / persisted).resolve()
    manifest = {
        "schema_version": 2,
        "benchmark": "ASI-Bench",
        "seed": 31415,
        "task_id": request.task_id,
        "instance_id": request.instance_id,
        "prompt_level": request.prompt_level,
        "attempt_id": "native-attempt-1",
        "run_result": str(result_path.resolve()),
        "prediction_dir": str(prediction),
        "instance_dir": str(instance),
        "tasks_dir": str(tasks),
        "harness": "agent-infra-fixture",
        "model": "none",
        "sandbox": "none",
        "scorer_revision": json.loads(scorer_policy.read_text(encoding="utf-8"))["source_revision"],
    }
    manifest_path = root / "benchflow_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    score_path = root / "benchflow_score.json"
    score_manifest_file(manifest_path, score_path)
    score = json.loads(score_path.read_text(encoding="utf-8"))
    summary = {
        "native_exit_code": completed.returncode,
        "task_id": request.task_id,
        "instance_id": request.instance_id,
        "prompt_level": request.prompt_level,
        "local_score": score.get("score"),
        "local_score_official": score.get("official"),
        "evaluation_status": score.get("evaluation_status"),
        "attempt_status": score.get("attempt_status"),
        "official_score": None,
        "submission": "not_requested",
    }
    (root / "native-result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(run(Request.model_validate_json(sys.argv[1])))
