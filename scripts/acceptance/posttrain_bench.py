"""BM04 installed-wheel acceptance; model-free and without scheduler/GPU/model calls."""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REVISION = "3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1"


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    checkout = Path(os.environ.get("POSTTRAIN_BENCH_CHECKOUT", ""))
    if not checkout.is_dir():
        raise SystemExit("set POSTTRAIN_BENCH_CHECKOUT to the pinned PostTrainBench checkout")
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise SystemExit("POSTTRAIN_BENCH_CHECKOUT is not the BM04 pinned revision")
    wheels = list((root / "dist").glob("agent_infra-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("build exactly one core wheel with uv build first")
    adapter = root / "adapters/posttrain-bench"
    task = checkout / "src/eval/tasks/gsm8k"

    with tempfile.TemporaryDirectory(prefix="agent-infra-bm04-") as directory:
        scratch = Path(directory)
        subprocess.run(
            ["uv", "build", "--project", str(adapter), "--wheel", "--out-dir", str(scratch)],
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "venv",
                "--python",
                (root / ".python-version").read_text().strip(),
                str(scratch / "venv"),
            ],
            check=True,
        )
        python = scratch / "venv/bin/python"
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheels[0]),
                str(next(scratch.glob("agent_infra_posttrain_bench-*.whl"))),
            ],
            check=True,
        )
        for name in ("adapters.toml", "request.json", "capabilities.json"):
            shutil.copyfile(adapter / name, scratch / name)
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

        def cli(*arguments: str) -> dict:
            result = subprocess.run(
                [str(scratch / "venv/bin/agent-infra"), "benchmark", *arguments],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr + result.stdout
            return json.loads(result.stdout)

        config = ("--config", "adapters.toml")
        state = ("--state-dir", str(scratch / "state"))
        inspected = cli("inspect", "posttrain-bench", "--source", str(task), *config)
        assert inspected["units"][0]["unit_id"] == "gsm8k"
        assert inspected["units"][0]["kind"] == "native_job"
        cli(
            "plan",
            "posttrain-bench",
            "--source",
            str(task),
            "--request",
            "request.json",
            "--output",
            "plan.json",
            *config,
        )
        checked = cli("check", "plan.json", "--capabilities", "capabilities.json", *config)
        assert checked["compatible"] is True
        cli("prepare", "plan.json", "--output", "execution.json", *config)
        run = cli(
            "run",
            "execution.json",
            "--operation-id",
            "bm04-engineering",
            "--capabilities",
            "capabilities.json",
            "--allow-native-runtime",
            *config,
            *state,
        )
        deadline = time.monotonic() + 30
        while run["state"] != "finished" and time.monotonic() < deadline:
            time.sleep(0.1)
            run = cli("status", run["run_id"], *config, *state)
        assert run["state"] == "finished", run
        result = run["result"]["native_result"]
        assert result["protocol"] == "valid" and result["engineering_fixture"] is True
        assert result["model_handoff"]["immutable"] is True
        assert result["score_eligible"] is False and result["official"] is False
        assert len(cli("artifacts", run["run_id"], *config, *state)["items"]) == 1
        assert cli("queue", *state)["leases"][0]["state"] == "released"
    print("BM04: native prompt, judge evidence, model handoff and Records passed.")


if __name__ == "__main__":
    main()
