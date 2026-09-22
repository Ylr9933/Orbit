"""Install the built wheel into a disposable environment outside the source tree."""

import json
import os
import subprocess
import sys
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
        subprocess.run(
            [str(environment / "bin/agent-infra"), "mcp", "--help"],
            cwd=scratch,
            env=env,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "from pathlib import Path; "
                "from agent_infra.environments import _research_runtime; "
                "from agent_infra.gateways.mcp.research import create_mcp; "
                "assert Path(_research_runtime.__file__).is_file()",
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

        def research(*arguments: str) -> dict[str, object]:
            result = subprocess.run(
                [cli, "project", "research", *arguments, "--state-dir", str(state)],
                cwd=workspace,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            return dict(json.loads(result.stdout))

        payload = scratch / "draft.json"
        payload.write_text(
            json.dumps({"schema_version": 1, "brief": {"question": "Compare two methods"}})
        )
        saved = research(
            "save",
            project["project_id"],
            "--file",
            str(payload),
            "--expected-revision",
            "0",
            "--reason",
            "Initial proposal",
        )
        assert saved["projection"]["status"] == "pending"
        assert document.read_text() == "User research notes\n"
        imported = research(
            "import-notes",
            project["project_id"],
            "--file",
            str(document),
            "--section",
            "background",
            "--expected-revision",
            "1",
            "--reason",
            "User notes",
        )
        assert imported["projection"]["status"] == "ready"
        assert research("context", project["project_id"])["research_revision"] == 2
        instructions = research("skill", project["project_id"])
        assert "references/commands.md" in instructions["files"]
        installed = research("skill", project["project_id"], "--install")
        assert (Path(installed["skill_path"]) / "SKILL.md").is_file()
        subprocess.run(
            [
                str(python),
                str(root / "scripts/acceptance/project_compilation.py"),
                "--cli",
                cli,
                "--output-dir",
                str(scratch / "compilation-acceptance"),
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        subprocess.run(
            [cli, "environment", "--help"],
            cwd=scratch,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                "from agent_infra.environments.preparation_api import EnvironmentIntent; "
                "from agent_infra.environments.preparation_docker "
                "import DockerEnvironmentPreparer; "
                "from agent_infra.gateways.mcp.environment import add_environment_tools; "
                "assert EnvironmentIntent.from_dict("
                "{'goal':'smoke','base_image':'python'}).cpu == 1",
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        for command in ("study", "planner"):
            subprocess.run(
                [cli, command, "--help"], cwd=scratch, env=env, check=True, capture_output=True
            )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "from pathlib import Path; "
                "from agent_infra.environments import planner_client; "
                "from agent_infra.projects.analysis import AnalysisService; "
                "assert Path(planner_client.__file__).is_file()",
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
    print("Wheel installation and isolated package/CLI smoke checks passed.")
    subprocess.run(
        [sys.executable, str(root / "scripts/ci/smoke_benchmark_adapter.py")],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()
