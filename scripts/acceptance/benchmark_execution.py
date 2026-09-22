"""BM01 installed-wheel acceptance; real short CPU process, no models/Docker/GPU.

Run after uv build. Installs into a disposable venv outside the source checkout.
Only its temporary workspace and single <=30s example operation are touched.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    wheels = list((root / "dist").glob("agent_infra-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one core wheel with uv build first")
    example = root / "examples/benchmark-execution"
    with tempfile.TemporaryDirectory(prefix="agent-infra-bm01-") as directory:
        scratch = Path(directory)
        subprocess.run(
            ["uv", "build", "--project", str(example), "--wheel", "--out-dir", str(scratch)],
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
                str(next(scratch.glob("agent_infra_benchmark_process_example-*.whl"))),
            ],
            check=True,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH" and not key.startswith("AGENT_INFRA_")
        }
        shutil.copytree(example / "fixture", scratch / "fixture")
        for name in ("adapters.toml", "request.json", "capabilities.json"):
            shutil.copyfile(example / name, scratch / name)

        def cli(*arguments: str, code: int = 0) -> dict:
            result = subprocess.run(
                [str(scratch / "venv/bin/agent-infra"), "benchmark", *arguments],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert result.returncode == code, result.stderr + result.stdout
            return json.loads(result.stderr if code == 2 else result.stdout)

        config = ("--config", "adapters.toml")
        state = ("--state-dir", str(scratch / "state"))
        cli(
            "plan",
            "process-demo",
            "--source",
            "fixture",
            "--request",
            "request.json",
            "--output",
            "plan.json",
            *config,
        )
        cli("check", "plan.json", "--capabilities", "capabilities.json", *config)
        cli("prepare", "plan.json", "--output", "execution.json", *config)
        arguments = (
            "run",
            "execution.json",
            "--operation-id",
            "bm01-installed",
            "--capabilities",
            "capabilities.json",
            *config,
            *state,
        )
        assert "allow-host-process" in str(cli(*arguments, code=2))
        assert not (scratch / "state").exists()
        run = cli(*arguments, "--allow-host-process")
        run_id = run["run_id"]
        second_arguments = tuple(
            "bm05a-second" if value == "bm01-installed" else value for value in arguments
        )
        second = cli(*second_arguments, "--allow-host-process")
        second_run_id = second["run_id"]
        assert second["state"] == "queued" and not second["slot_held"]
        queued = cli("queue", *state)
        assert [item["run_id"] for item in queued["queued"]] == [second_run_id]
        assert len([item for item in queued["leases"] if item["state"] != "released"]) == 1
        try:
            # Each call is a fresh CLI/coordinator. A lost client does not own runner lifetime.
            assert cli(*arguments, "--allow-host-process")["run_id"] == run_id
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                run = cli("status", run_id, *state)
                if run["state"] == "finished":
                    break
                time.sleep(0.1)
            assert run["state"] == "finished", run
            assert run["result"]["execution"] == "completed" and not run["slot_held"]
            assert run["result"]["evaluation"] == "not_interpreted"
            assert run["handle"]["native_id"]
            assert len(cli("artifacts", run_id, *state)["items"]) == 1
            events = cli("events", run_id, *state)["items"]
            assert len(events) == 5 and len({item["event_id"] for item in events}) == 5
            # Inspect with public Records readers in the installed environment, not internals.
            check = (
                "import json,sys; from pathlib import Path; "
                "from agent_infra.records.api import BlobRef; "
                "from agent_infra.records.local import LocalRecordsStore; "
                "s=LocalRecordsStore(Path(sys.argv[1])); "
                "a=s.list_artifacts(sys.argv[2]); assert len(a)==1; "
                "manifest=json.load(s.open_blob(a[0].manifest_blob)); "
                "entry=next(f for f in manifest['files'] if f['path']=='outputs/result.json'); "
                "assert json.load(s.open_blob(BlobRef(**entry['blob'])))=={'sum':10}; "
                "attempt=s.get_attempt(sys.argv[2]); "
                "raw=s.open_blob(BlobRef(**attempt.result['stream']['blob'])).read(); "
                "assert json.loads(raw)=={'sum':10}; "
                "print(json.dumps({'artifacts':len(a)}))"
            )
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-c",
                    check,
                    str(scratch / "state/benchmarks/records"),
                    run["attempt_id"],
                ],
                cwd=scratch,
                env=env,
                check=True,
            )
            snapshots = list((scratch / "state/benchmarks/native").glob("*/collected"))
            assert len(snapshots) >= 1
            assert json.loads((snapshots[0] / "outputs/result.json").read_bytes()) == {"sum": 10}
            assert cli(*arguments, "--allow-host-process")["result"] == run["result"]

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                second = cli("status", second_run_id, *state)
                if second["state"] == "finished":
                    break
                time.sleep(0.1)
            assert second["state"] == "finished" and second["result"]["execution"] == "completed"
            assert second["lease_state"] == "released"
            assert cli("reconcile", *state)["runs"] == []
            leases = cli("queue", *state)["leases"]
            assert len(leases) == 2 and all(item["state"] == "released" for item in leases)
        finally:
            # On failure, request cancellation and wait for the owned <=30s supervisor.
            current = cli("cancel", run_id, *state)
            deadline = time.monotonic() + 35
            while current["state"] != "finished" and time.monotonic() < deadline:
                time.sleep(0.1)
                current = cli("status", run_id, *state)
            if current["state"] != "finished":
                raise RuntimeError(f"owned execution did not finalize: {current}")
            second_current = cli("cancel", second_run_id, *state)
            deadline = time.monotonic() + 35
            while second_current["state"] != "finished" and time.monotonic() < deadline:
                time.sleep(0.1)
                second_current = cli("status", second_run_id, *state)
            if second_current["state"] != "finished":
                raise RuntimeError(f"queued execution did not finalize: {second_current}")
    print("BM05-A: independent wheels, FIFO queue, durable leases, restart and Records passed.")


if __name__ == "__main__":
    main()
