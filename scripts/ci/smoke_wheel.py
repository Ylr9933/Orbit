"""Install the built wheel into a disposable environment outside the source tree."""

import json
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
            ["uv", "pip", "install", "--python", str(python), str(wheels[0])],
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
        request = scratch / "resource.yaml"
        request.write_text(
            "version: 1\nrequest_id: smoke\nresources:\n  cpu: 1\n  memory: 1GiB\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                str(environment / "bin/agent-infra"),
                "resource",
                "validate",
                str(request),
            ],
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
        cli = str(environment / "bin/agent-infra")
        workspace = scratch / "research"
        state = scratch / "state"
        init = [
            cli,
            "init",
            str(workspace),
            "--goal",
            "Compare position encodings",
            "--state-dir",
            str(state),
        ]
        preview = subprocess.run(
            [*init, "--dry-run"],
            cwd=scratch,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "docs/background.md" in json.loads(preview.stdout)["files"]
        assert not workspace.exists() and not state.exists()
        created = subprocess.run(
            init,
            cwd=scratch,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        project = json.loads(created.stdout)["project"]
        document = workspace / "docs/background.md"
        document.write_text("User research notes\n", encoding="utf-8")
        repeated = subprocess.run(
            init,
            cwd=scratch,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert json.loads(repeated.stdout)["project"] == project
        assert document.read_text(encoding="utf-8") == "User research notes\n"
        shown = subprocess.run(
            [cli, "project", "show", project["project_id"], "--state-dir", str(state)],
            cwd=workspace,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert json.loads(shown.stdout)["manifest_matches"] is True
    print("Wheel installation and isolated package/CLI smoke checks passed.")


if __name__ == "__main__":
    main()
