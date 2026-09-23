"""Model-free BM04 protocol exercise; native jobs are launched by the Condor backend."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .handoff import finalize
from .request import Request
from .source import runner_digest, task_digest


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def run(request: Request) -> int:
    if request.mode != "engineering":
        raise ValueError("native PostTrainBench jobs must be submitted by the HTCondor backend")
    root = Path.cwd()
    checkout = request.checkout()
    task = checkout / "src" / "eval" / "tasks" / request.task
    if task_digest(task) != request.task_digest or runner_digest(checkout) != request.runner_digest:
        raise ValueError("PostTrainBench source changed after planning")

    result = root / "engineering-result"
    model = result / "final_model"
    model.mkdir(parents=True)
    prompt = subprocess.run(
        [
            sys.executable,
            "src/eval/general/get_prompt.py",
            "--agent",
            "codex",
            "--model-to-train",
            request.model_to_train,
            "--benchmark-id",
            request.task,
            "--num-hours",
            str(request.num_hours),
            "--num-gpus",
            "1",
        ],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (result / "prompt.txt").write_text(prompt, encoding="utf-8")
    (result / "solve_out.txt").write_text("model-free engineering fixture\n", encoding="utf-8")
    (result / "solve_parsed.txt").write_text("No Agent or model was invoked.\n", encoding="utf-8")
    (result / "time_taken.txt").write_text("00:00:01\n", encoding="utf-8")
    (result / "system_monitor.log").write_text(
        "engineering fixture; no GPU allocated\n", encoding="utf-8"
    )
    _write(result / "metrics.json", {"accuracy": 0.125, "engineering_fixture": True})
    _write(
        result / "judgement_gpt5_4.json",
        {"contamination": False, "disallowed_model": False, "engineering_fixture": True},
    )
    _write(
        result / "judgement_api.json",
        {"disallowed_api_usage": False, "engineering_fixture": True},
    )
    _write(
        result / "judgement_ptb_lookup.json",
        {"disallowed_ptb_lookup": False, "engineering_fixture": True},
    )
    _write(result / "judgement_general.json", {"general_anomaly": False})
    _write(
        model / "config.json",
        {"model_type": "engineering-fixture", "source": request.model_to_train},
    )
    (model / "model.safetensors").write_bytes(b"BM04 engineering fixture\n")
    finalize(request, result, root)
    return 0


if __name__ == "__main__":
    sys.exit(run(Request.model_validate_json(sys.argv[1])))
