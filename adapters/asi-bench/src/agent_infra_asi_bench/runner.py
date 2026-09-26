"""Run one pinned ASI-Bench public attempt and score its materialized output."""

import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

from ai4sci_bench.benchflow import score_manifest_file

from agent_infra.contracts.files import content_digest

from .docker_proxy import summarize
from .evidence import capture
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


def _evidence_summary(evidence: dict | None) -> dict:
    if evidence is None:
        return {}
    return {
        "evidence": {
            "capture_status": evidence["capture_status"],
            "trajectory": evidence["trajectory"],
            "calls": evidence["calls"],
            "docker": evidence["docker"],
        }
    }


def _write_failure(
    root: Path, request: Request, exit_code: int, reason: str, evidence: dict | None
) -> int:
    summary = {
        "native_exit_code": exit_code,
        "task_id": request.task_id,
        "instance_id": request.instance_id,
        "prompt_level": request.prompt_level,
        "evaluation_status": "failed",
        "attempt_status": "failed",
        "failure_reason": reason,
        "official_score": None,
        "submission": "not_requested",
        **_evidence_summary(evidence),
    }
    (root / "native-result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 1


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
    ]
    auth = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codex" / "auth.json"
    if not auth.is_file() or auth.is_symlink() or auth.stat().st_uid != os.getuid():
        raise ValueError("a private host Codex auth.json owned by this user is required")
    docker = shutil.which("docker", path=os.defpath)
    if docker is None:
        raise ValueError("Docker CLI is unavailable")
    proxy = root / "docker-proxy"
    proxy.mkdir(mode=0o700)
    wrapper = proxy / "docker"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "from agent_infra_asi_bench.docker_proxy import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    observations = root / "docker-observations.jsonl"
    observations.touch(mode=0o600)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(auth.parent.parent),
            "PATH": str(proxy) + os.pathsep + os.defpath,
            "AGENT_INFRA_DOCKER_BIN": docker,
            "AGENT_INFRA_ASI_RUN": root.name,
            "AGENT_INFRA_DOCKER_OBSERVATIONS": str(observations),
            "AGENT_INFRA_ASI_BUILD_NETWORK": request.docker_network,
        }
    )
    if request.docker_network == "host":
        environment["AI4SCI_DOCKER_NETWORK"] = "host"
    if request.proxy_url:
        environment.update(
            http_proxy=request.proxy_url,
            https_proxy=request.proxy_url,
            HTTP_PROXY=request.proxy_url,
            HTTPS_PROXY=request.proxy_url,
        )
    command.extend(
        (
            "--agent",
            "codex_cli",
            "--agent-config",
            json.dumps({"model": request.model, "effort": request.effort}),
            "--sandbox",
            "os",
        )
    )
    command.extend(
        (
            "--parallel",
            "1",
            "--retries",
            "1",
            "--timeout",
            str(request.timeout_seconds),
            "--output-dir",
            str(native),
        )
    )
    completed = subprocess.run(command, check=False, env=environment)
    result_path = _single_result(native)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("task_id") != request.task_id or result.get("instance_id") != request.instance_id:
        raise ValueError("native runner changed task or instance identity")
    if result.get("prompt_level") != request.prompt_level:
        raise ValueError("native runner changed prompt level")
    provenance = result.get("provenance", {}).get("sandbox", {})
    observations = []
    for line in (root / "docker-observations.jsonl").read_text().splitlines():
        try:
            observations.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    evidence = capture(
        result_path,
        result,
        root / "evidence",
        docker=summarize(observations, provenance.get("image_identity")),
    )
    persisted = result.get("agent_output", {}).get("persisted_outputs", {}).get("dir")
    if not persisted:
        return _write_failure(
            root, request, completed.returncode, "native prediction absent", evidence
        )
    if persisted != Path(persisted).name or persisted in {".", ".."}:
        return _write_failure(
            root, request, completed.returncode, "unsafe prediction path", evidence
        )
    prediction = result_path.parent / persisted
    if not prediction.is_dir() or prediction.is_symlink():
        return _write_failure(
            root, request, completed.returncode, "prediction directory missing", evidence
        )
    prediction = prediction.resolve()
    if not (
        provenance.get("effective_mode") == "os"
        and provenance.get("verification_status") == "docker_container"
        and provenance.get("image_identity")
    ):
        return _write_failure(
            root, request, completed.returncode, "Docker OS provenance absent", evidence
        )
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
        "harness": "codex_cli",
        "model": request.model,
        "sandbox": "os",
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
        **_evidence_summary(evidence),
    }
    (root / "native-result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(run(Request.model_validate_json(sys.argv[1])))
