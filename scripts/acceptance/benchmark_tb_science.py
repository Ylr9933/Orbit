"""Opt-in BM02-A real Docker acceptance, using installed wheels and native Oracle.

Run with the isolated runtime's Python. Source must be the pinned symbolic-regression
checkout. No model calls/GPU; <=1.1 CPU/2176 MiB running containers at a time.
Each native operation has a 20-minute observation budget, then scoped cancellation.
Raw native benchmark materials stay in the supplied private output directory.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-docker", action="store_true", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--capabilities", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    cli = str(Path(sys.executable).with_name("agent-infra"))
    config = ["--config", str(args.config.absolute())]
    state = ["--state-dir", str(root / "state")]

    def command(*argv: str) -> dict:
        result = subprocess.run(
            [cli, "benchmark", *argv], capture_output=True, text=True, timeout=60, check=True
        )
        return json.loads(result.stdout)

    def await_result(run: dict) -> dict:
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            run = command("status", run["run_id"], *state, *config)
            if run["state"] == "finished":
                return run
            time.sleep(1)
        command("cancel", run["run_id"], *state, *config)
        raise RuntimeError("acceptance timeout; cancellation requested, inspect owned state")

    command(
        "plan",
        "tb-science",
        "--source",
        str(args.source.absolute()),
        *config,
        "--request",
        str(args.request.absolute()),
        "--output",
        str(root / "plan.json"),
    )
    command("prepare", str(root / "plan.json"), *config, "--output", str(root / "execution.json"))

    def submit(operation: str) -> dict:
        return command(
            "run",
            str(root / "execution.json"),
            *config,
            *state,
            "--capabilities",
            str(args.capabilities.absolute()),
            "--operation-id",
            operation,
            "--allow-native-runtime",
        )

    run = await_result(submit("oracle"))
    (root / "platform-result.json").write_text(json.dumps(run, indent=2))
    assert run["result"]["evaluation"] == "scored" and not run["slot_held"]
    repeat = submit("oracle")
    assert repeat["run_id"] == run["run_id"]  # No duplicate launch after completion.
    workspace = root / "state/benchmarks/workspaces" / run["run_id"]
    trial = next((workspace / "trials").iterdir())

    # Same frozen native artifacts, direct Harbor regrade; no platform Run/Records path.
    from agent_infra_harbor.request import Request

    from agent_infra.contracts.files import content_digest

    source = Request.model_validate_json(
        json.loads((root / "execution.json").read_text())["invocation"]["command"]["argv"][-1]
    )
    original_artifacts = content_digest(trial / "artifacts")
    regrade = root / "native-regrade"
    regrade.mkdir(mode=0o700)
    with (regrade / "combined.log").open("w") as stream:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agent_infra_harbor.runner",
                source.model_copy(update={"source_trial": str(trial)}).model_dump_json(),
            ],
            cwd=regrade,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        try:
            code = process.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=100)
            raise
    assert code == 0
    assert content_digest(trial / "artifacts") == original_artifacts
    raw = json.loads(next((regrade / "trials").glob("*/result.json")).read_text())
    assert raw["verifier_result"]["rewards"] == run["result"]["native_result"]["metrics"]
    assert json.loads((regrade / "native-cleanup.json").read_text())["complete"]

    cancelled = submit("cancel-after-container-start")
    cancel_workspace = root / "state/benchmarks/workspaces" / cancelled["run_id"]
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        owner = cancel_workspace / "native-ownership.json"
        if owner.exists():
            projects = json.loads(owner.read_text())["projects"]
            if any(
                subprocess.check_output(
                    [
                        "docker",
                        "ps",
                        "-q",
                        "--filter",
                        "label=com.docker.compose.project=" + project,
                    ],
                    text=True,
                ).strip()
                for project in projects
            ):
                break
        time.sleep(0.1)
    else:
        command("cancel", cancelled["run_id"], *state, *config)
        raise RuntimeError("no task container observed within acceptance budget")
    command("cancel", cancelled["run_id"], *state, *config)
    cancelled = await_result(cancelled)
    assert cancelled["result"]["execution"] == "cancelled" and not cancelled["slot_held"]
    report = {
        "platform_run": run["run_id"],
        "cancelled_run": cancelled["run_id"],
        "reward": raw["verifier_result"]["rewards"],
        "same_output_regrade": "passed",
        "duplicate_submit": "passed",
        "cancel_cleanup": "passed",
        "model_calls": 0,
        "source_artifacts_digest": original_artifacts,
    }
    (root / "acceptance.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
