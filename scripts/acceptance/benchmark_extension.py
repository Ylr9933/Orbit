"""BM07 independent package rehearsal: a new synthetic bench needs no core edits.

Build the core wheel first. Uses one disposable local CPU process, no model/Docker/GPU.
The temporary package is copied and renamed from the public process example, then installed
beside the core wheel into an isolated venv. All state is task-owned and removed on exit.
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
    with tempfile.TemporaryDirectory(prefix="agent-infra-bm07-") as directory:
        scratch = Path(directory)
        package = scratch / "third-party"
        shutil.copytree(example, package)
        old_module = package / "src/agent_infra_benchmark_process_example"
        new_module = package / "src/external_sum_benchmark"
        old_module.rename(new_module)
        metadata = package / "pyproject.toml"
        metadata.write_text(
            metadata.read_text()
            .replace("agent-infra-benchmark-process-example", "external-sum-benchmark")
            .replace('process-demo = "', 'external-sum = "')
            .replace(
                "agent_infra_benchmark_process_example:Adapter", "external_sum_benchmark:Adapter"
            )
        )
        source = new_module / "__init__.py"
        source.write_text(
            source.read_text()
            .replace('adapter_id="process-demo"', 'adapter_id="external-sum"')
            .replace('benchmark="synthetic-process"', 'benchmark="external-sum"')
        )
        config = package / "adapters.toml"
        config.write_text(
            config.read_text()
            .replace("agent-infra-benchmark-process-example", "external-sum-benchmark")
            .replace("process-demo", "external-sum")
        )
        capabilities = package / "capabilities.json"
        capabilities.write_text(
            capabilities.read_text().replace(
                '"adapter_id": "process-demo"', '"adapter_id": "external-sum"'
            )
        )
        subprocess.run(
            ["uv", "build", "--project", str(package), "--wheel", "--out-dir", str(scratch)],
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
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(scratch / "venv/bin/python"),
                str(wheels[0]),
                str(next(scratch.glob("external_sum_benchmark-*.whl"))),
            ],
            check=True,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH" and not key.startswith("AGENT_INFRA_")
        }

        def cli(*arguments: str) -> dict:
            result = subprocess.run(
                [str(scratch / "venv/bin/agent-infra"), "benchmark", *arguments],
                cwd=package,
                env=env,
                capture_output=True,
                text=True,
                timeout=25,
            )
            if result.returncode:
                raise RuntimeError(result.stderr + result.stdout)
            return json.loads(result.stdout)

        state = ("--state-dir", str(scratch / "state"))
        config_arg = ("--config", str(config))
        cli(
            "plan",
            "external-sum",
            "--source",
            "fixture",
            "--request",
            "request.json",
            "--output",
            str(scratch / "plan.json"),
            *config_arg,
        )
        checked = cli(
            "check", str(scratch / "plan.json"), "--capabilities", str(capabilities), *config_arg
        )
        assert checked["compatible"] is True
        cli(
            "prepare",
            str(scratch / "plan.json"),
            "--output",
            str(scratch / "execution.json"),
            *config_arg,
        )
        run = cli(
            "run",
            str(scratch / "execution.json"),
            "--operation-id",
            "external-sum-once",
            "--capabilities",
            str(capabilities),
            "--allow-host-process",
            *config_arg,
            *state,
        )
        run_id = run["run_id"]
        deadline = time.monotonic() + 15
        try:
            while run["state"] != "finished" and time.monotonic() < deadline:
                time.sleep(0.1)
                run = cli("status", run_id, *state)
            assert run["state"] == "finished" and run["result"]["execution"] == "completed"
            assert cli("artifacts", run_id, *state)["items"]
            matrix = {
                "schema_version": 1,
                "entries": [
                    {
                        "alias": "external-sum",
                        "adapter_id": "external-sum",
                        "distribution": "external-sum-benchmark",
                        "adapter_version": "0.1.0",
                        "suite_digest": json.loads((scratch / "plan.json").read_text())["plan"][
                            "suite"
                        ]["source"]["digest"],
                        "runner_digest": json.loads((scratch / "plan.json").read_text())["plan"][
                            "suite"
                        ]["runner"]["digest"],
                        "profile": "sum-v1",
                        "backend": "managed-process-v1",
                        "agent": "cooperative-fixture",
                        "agent_version": "1",
                        "model": "none",
                        "level": "runnable",
                        "evidence": [f"run:{run_id}"],
                        "official_submission": "unsupported",
                        "limitations": ["synthetic CPU fixture"],
                    }
                ],
            }
            matrix_file = scratch / "matrix.json"
            matrix_file.write_text(json.dumps(matrix))
            assert (
                cli("compatibility", "publish", "--file", str(matrix_file), *config_arg, *state)[
                    "entries"
                ]
                == 1
            )
            assert (
                cli("compatibility", "show", *state)["entries"][0]["adapter_id"] == "external-sum"
            )
            inspection = (
                "import json,sys; from pathlib import Path; "
                "from agent_infra.bootstrap.benchmark_console import BenchmarkConsole; "
                "d=BenchmarkConsole(Path(sys.argv[1])).snapshot(); "
                "assert d['runs'][0]['adapter']=='external-sum'; "
                "assert d['compatibility'][0]['level']=='runnable'; "
                "print(json.dumps({'runs':len(d['runs']),'matrix':len(d['compatibility'])}))"
            )
            subprocess.run(
                [str(scratch / "venv/bin/python"), "-I", "-c", inspection, str(scratch / "state")],
                cwd=package,
                env=env,
                check=True,
            )
        finally:
            current = cli("cancel", run_id, *state)
            deadline = time.monotonic() + 35
            while current["state"] != "finished" and time.monotonic() < deadline:
                time.sleep(0.1)
                current = cli("status", run_id, *state)
            if current["state"] != "finished":
                raise RuntimeError("owned example job did not finalize")
    print("BM07 independent adapter, queue, Records, compatibility and dashboard passed")


if __name__ == "__main__":
    main()
