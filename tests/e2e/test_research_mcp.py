"""Real stdio MCP, HTTP daemon and CPU Docker. No LLM involved."""

import asyncio
import json
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_infra.gateways.cli.research_runtime import ResearchClient
from agent_infra.projects import InitRequest
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.service import ProjectService

pytestmark = pytest.mark.e2e
CLI = str(Path(sys.executable).parent / "agent-infra")


@contextmanager
def daemon(state):
    with (state.parent / "controller.log").open("ab") as output:
        process = subprocess.Popen(
            [
                CLI,
                "controller",
                "serve",
                "--state-dir",
                str(state),
                "--port",
                "0",
                "--cpu",
                "1",
                "--memory-gib",
                "0.25",
                "--model-proxy",
                "direct",
            ],
            stdout=output,
            stderr=output,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                endpoint = state / "controller/endpoint.json"
                if endpoint.exists() and json.loads(endpoint.read_text())["pid"] == process.pid:
                    break
                assert process.poll() is None, (state.parent / "controller.log").read_text()
                time.sleep(0.05)
            else:
                pytest.fail("controller startup timed out")
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(40)
            assert process.returncode in (0, -9), (state.parent / "controller.log").read_text()


def initialize(tmp_path):
    state = tmp_path / "state"
    project = ProjectService(LocalProjectStore(state / "projects")).initialize(
        InitRequest(goal="CPU toy training", directory=tmp_path / "project")
    )
    return state, project.project_id


def test_real_mcp_disconnect_reconnect_and_stop(tmp_path):
    state, project = initialize(tmp_path)
    with daemon(state):

        async def scenario():
            params = StdioServerParameters(
                command=CLI,
                args=[
                    "mcp",
                    "--state-dir",
                    str(state),
                    "--project-id",
                    project,
                    "--session-id",
                    "test-session",
                ],
            )

            async def tool(session, name, args):
                result = await session.call_tool(name, args)
                assert not result.isError, result
                return result.structuredContent

            async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                names = {t.name for t in (await client.list_tools()).tools}
                assert {
                    "environment_open",
                    "job_start",
                    "job_logs",
                    "workspace_write",
                    "artifact_save",
                } <= names
                context = await tool(client, "project_context", {})
                assert context["project"]["project_id"] == project
                run = await tool(
                    client,
                    "environment_open",
                    {"image": "python:3.12-slim", "memory_gib": 0.25, "operation_id": "open"},
                )
                job = await tool(
                    client,
                    "job_start",
                    {
                        "run_id": run["run_id"],
                        "argv": [
                            "python3",
                            "-u",
                            "-c",
                            'import time; print("still running",flush=True); time.sleep(120)',
                        ],
                        "operation_id": "start",
                    },
                )
            # The first stdio process has exited, but its Docker Job must remain alive.
            assert (
                ResearchClient(state, project, "observer").call("status", run_id=run["run_id"])[
                    "state"
                ]
                == "running"
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                logs = await tool(
                    client, "job_logs", {"run_id": run["run_id"], "job_id": job["job_id"]}
                )
                assert logs["state"] == "running" and "still running" in logs["text"]
                stopped = await tool(
                    client,
                    "job_stop",
                    {"run_id": run["run_id"], "job_id": job["job_id"], "operation_id": "stop"},
                )
                assert stopped["state"] == "cancelled"
                denied = await client.call_tool(
                    "workspace_read", {"run_id": run["run_id"], "path": "../secret"}
                )
                assert denied.isError
                closed = await tool(
                    client, "environment_close", {"run_id": run["run_id"], "operation_id": "close"}
                )
                assert closed["result"]["cleanup_complete"] and closed["result"]["lease_released"]

        asyncio.run(scenario())


def test_controller_sigkill_marks_research_interrupted(tmp_path):
    state, project = initialize(tmp_path)
    with daemon(state) as process:
        client = ResearchClient(state, project, "session")
        run = client.call(
            "open", operation_id="open", image="python:3.12-slim", memory_bytes=256 * 1024**2
        )
        job = client.call(
            "start",
            operation_id="start",
            run_id=run["run_id"],
            argv=[
                "python3",
                "-u",
                "-c",
                'import time; print("checkpoint",flush=True); time.sleep(120)',
            ],
        )
        deadline = time.monotonic() + 15
        while not client.call("logs", run_id=run["run_id"], job_id=job["job_id"])["text"]:
            assert time.monotonic() < deadline
            time.sleep(0.1)
        process.kill()
        process.wait(10)
    with daemon(state):
        client = ResearchClient(state, project, "session")
        status = client.call("status", run_id=run["run_id"])
        assert status["result"]["status"] == "interrupted"
        assert status["result"]["cleanup_complete"]
        assert status["jobs"][0]["state"] == "interrupted"
        assert (
            "checkpoint" in client.call("logs", run_id=run["run_id"], job_id=job["job_id"])["text"]
        )
        assert (
            client.call(
                "open", operation_id="open", image="python:3.12-slim", memory_bytes=256 * 1024**2
            )["run_id"]
            == run["run_id"]
        )
        again = client.call(
            "open", operation_id="fresh", image="python:3.12-slim", memory_bytes=256 * 1024**2
        )
        client.call("close", operation_id="close", run_id=again["run_id"])
