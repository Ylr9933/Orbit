"""BM03 installed-wheel acceptance; pinned model-free family, no Docker/GPU/model."""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REVISION = "f8223517ae7491e776b69793d9f11e9d074ab42e"


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    checkout = Path(os.environ.get("PAST_BENCH_CHECKOUT", ""))
    if not checkout.is_dir():
        raise SystemExit("set PAST_BENCH_CHECKOUT to the pinned PAST-Bench checkout")
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise SystemExit("PAST_BENCH_CHECKOUT is not the BM03 pinned revision")
    wheels = list((root / "dist").glob("agent_infra-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("build exactly one core wheel with uv build first")
    adapter = root / "adapters/past-bench"
    family = checkout / "self-evolve-tasks-v2/memory_ability/SM01_preference_adoption"

    with tempfile.TemporaryDirectory(prefix="agent-infra-bm03-") as directory:
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
                str(next(scratch.glob("agent_infra_past_bench-*.whl"))),
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
        inspected = cli("inspect", "past-bench", "--source", str(family), *config)
        assert inspected["units"][0]["episodes"] == 8
        assert inspected["units"][0]["conditions"] == 2
        cli(
            "plan",
            "past-bench",
            "--source",
            str(family),
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
            "bm03-engineering",
            "--capabilities",
            "capabilities.json",
            "--allow-native-runtime",
            *config,
            *state,
        )
        run_id = run["run_id"]
        deadline = time.monotonic() + 30
        while run["state"] != "finished" and time.monotonic() < deadline:
            time.sleep(0.1)
            run = cli("status", run_id, *config, *state)
        assert run["state"] == "finished", run
        result = run["result"]["native_result"]
        assert result["evaluation"] == "scored" and result["protocol"] == "valid"
        assert result["engineering_fixture"] is True and result["official"] is False
        assert result["conditions"] == ["with_persistence", "without_persistence"]
        assert result["metrics"]["paired_evaluation_score_delta"] > 0
        assert len(cli("artifacts", run_id, *config, *state)["items"]) == 1
        assert cli("queue", *state)["leases"][0]["state"] == "released"
    print("BM03: pinned family, paired state evidence, native aggregation and Records passed.")


if __name__ == "__main__":
    main()
