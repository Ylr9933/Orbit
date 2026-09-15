"""Install the built wheel into a disposable environment outside the source tree."""

import os
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    wheels = list((root / "dist").glob("agent_infra-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one agent-infra wheel in dist; run make build.")
    with tempfile.TemporaryDirectory(prefix="agent-infra-wheel-") as directory:
        scratch = Path(directory)
        environment = scratch / "venv"
        version = (root / ".python-version").read_text().strip()
        subprocess.run(["uv", "venv", "--python", version, str(environment)], check=True)
        python = environment / "bin/python"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheels[0])],
            check=True,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH" and not key.startswith("AGENT_INFRA_")
        }
        subprocess.run(
            [str(environment / "bin/agent-infra"), "config-check"],
            cwd=scratch,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import agent_infra.agents, agent_infra.environments, agent_infra.runs; "
                "import agent_infra.tasks, agent_infra.resources, agent_infra.records",
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        assert not (scratch / "var").exists(), "CLI unexpectedly created runtime state"
    print("Wheel installation and isolated package/CLI smoke checks passed.")


if __name__ == "__main__":
    main()
