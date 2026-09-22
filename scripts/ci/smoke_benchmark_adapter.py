"""Prove external wheel installation/enablement without source-tree imports or core edits.

Run after `uv build`. Creates only a temporary venv, adapter wheel and fixture plans.
No models, Docker, GPU, native benchmark commands or shared venv modifications.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    wheels = list((root / "dist").glob("agent_infra-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one core wheel in dist with uv build first")
    example = root / "examples/benchmark-adapter"
    with tempfile.TemporaryDirectory(prefix="agent-infra-bm00-") as directory:
        scratch = Path(directory)
        subprocess.run(
            ["uv", "build", "--project", str(example), "--wheel", "--out-dir", str(scratch)],
            check=True,
        )
        python = scratch / "venv/bin/python"
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
                str(python),
                str(wheels[0]),
                str(next(scratch.glob("agent_infra_benchmark_example-*.whl"))),
            ],
            check=True,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH" and not key.startswith("AGENT_INFRA_")
        }
        cli_path = scratch / "venv/bin/agent-infra"
        shutil.copytree(example / "fixtures", scratch / "fixtures")
        shutil.copytree(example / "tests", scratch / "tests")
        shutil.copyfile(example / "adapters.toml", scratch / "adapters.toml")
        shutil.copyfile(example / "capabilities.json", scratch / "capabilities.json")

        def cli(*args: str, code: int = 0) -> dict[str, object]:
            result = subprocess.run(
                [str(cli_path), "benchmark", *args],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == code, result.stderr + result.stdout
            return dict(json.loads(result.stderr if code == 2 else result.stdout))

        inventory = cli("adapters")
        assert inventory["installed"][0]["enabled_as"] == []
        rejected = cli("inspect", "demo", "--source", "fixtures/asi-like", code=2)
        assert "not explicitly enabled" in str(rejected)
        config = ("--config", "adapters.toml")
        for folder in sorted((scratch / "fixtures").iterdir()):
            source = str(folder)
            inspected = cli("inspect", "demo", "--source", source, *config)
            assert inspected["synthetic"] is True
            plan = str(scratch / f"{folder.name}.plan.json")
            planned = cli(
                "plan",
                "demo",
                "--source",
                source,
                "--request",
                str(folder / "request.json"),
                "--output",
                plan,
                *config,
            )
            assert planned["planning_valid"] is True and planned["runtime_ready"] is False
            assert cli("check", plan, *config, code=1)["compatible"] is False
            checked = cli("check", plan, "--capabilities", "capabilities.json", *config)
            assert checked["compatible"] is True and checked["runtime_ready"] is False
        subprocess.run(
            [str(python), "-I", "-m", "unittest", "discover", "-s", str(scratch / "tests")],
            cwd=scratch,
            env=env,
            check=True,
        )
        assert not (scratch / "var").exists(), "planning unexpectedly created execution state"
    print(
        "BM00: isolated external wheel + four synthetic protocol plans passed; no runtime executed."
    )


if __name__ == "__main__":
    main()
