"""Real CLI/MCP preparation lifecycle, host admission and interrupted-build recovery."""

import asyncio
import json
import subprocess
import time

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_infra.gateways.cli.research_runtime import ResearchClient
from tests.e2e.test_research_mcp import CLI, daemon, initialize

pytestmark = pytest.mark.e2e


def intent():
    return {
        "goal": "stdlib CPU research",
        "base_image": "python:3.12-slim",
        "template": "existing",
        "imports": ["json"],
        "memory_bytes": 256 * 1024**2,
    }


def test_cli_plan_mcp_validation_and_locked_research(tmp_path):
    state, project = initialize(tmp_path)
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(intent()))
    with daemon(state):
        command = [
            CLI,
            "environment",
            "plan",
            "--project-id",
            project,
            "--state-dir",
            str(state),
            "--file",
            str(path),
            "--operation-id",
            "cli-plan",
        ]
        plan = json.loads(subprocess.check_output(command, text=True))
        assert json.loads(subprocess.check_output(command, text=True))["plan_id"] == plan["plan_id"]

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
                    "integration",
                ],
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
                await client.initialize()

                async def tool(name, **arguments):
                    response = await client.call_tool(name, arguments)
                    assert not response.isError, response
                    return response.structuredContent

                await tool(
                    "environment_propose",
                    plan_id=plan["plan_id"],
                    expected_revision=0,
                    dependencies=[],
                    reason="reuse stdlib image",
                    operation_id="proposal",
                )
                built = await tool(
                    "environment_build", plan_id=plan["plan_id"], revision=1, operation_id="build"
                )
                assert (
                    await tool(
                        "environment_build",
                        plan_id=plan["plan_id"],
                        revision=1,
                        operation_id="build",
                    )
                )["attempts"][0]["attempt_id"] == built["attempts"][0]["attempt_id"]
                deadline = time.monotonic() + 40
                while True:
                    status = await tool("environment_plan_status", plan_id=plan["plan_id"])
                    if status["attempts"][-1]["status"] != "running":
                        break
                    assert time.monotonic() < deadline
                    await asyncio.sleep(0.1)
                ready = status["attempts"][-1]
                assert ready["status"] == "ready", status
                run = await tool(
                    "environment_open",
                    environment_lock=ready["lock"]["lock_id"],
                    memory_gib=0.25,
                    operation_id="open",
                )
                assert run["request"]["environment_lock"]["lock_id"] == ready["lock"]["lock_id"]
                await tool("environment_close", run_id=run["run_id"], operation_id="close")
                assert len((await tool("environment_plans"))["items"]) == 1

        asyncio.run(scenario())


def test_sigkill_recovery_retains_budget_without_replay(tmp_path):
    state, project = initialize(tmp_path)
    with daemon(state) as process:
        client = ResearchClient(state, project, "recovery")
        plan = client.call(
            "environment_plan",
            operation_id="intent",
            intent=intent()
            | {
                "template": "python-cpu",
                "network": True,
                "allowed_packages": ["six"],
                "max_attempts": 1,
                "attempt_seconds": 60,
            },
        )
        pid = plan["plan_id"]
        client.call(
            "environment_propose",
            operation_id="proposal",
            plan_id=pid,
            expected_revision=0,
            proposal={
                "dependencies": ["six==0.0.0"],
                "source": "user",
                "reason": "interrupt pip resolution",
            },
        )
        started = client.call("environment_build", operation_id="build", plan_id=pid, revision=1)
        attempt = started["attempts"][-1]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            journals = list((state / "controller/environments").glob("*/ownership.json"))
            acknowledged = [
                json.loads(p.read_text())
                for p in journals
                if json.loads(p.read_text())["lifecycle"] == "created"
            ]
            if acknowledged:
                break
            time.sleep(0.02)
        else:
            pytest.fail("no acknowledged build container")
        process.kill()
        process.wait(10)
    with daemon(state):
        client = ResearchClient(state, project, "recovery")
        plan = client.call("environment_status", plan_id=pid)
        assert plan["attempts"][-1]["status"] == "interrupted", plan
        assert plan["attempts"][-1]["cleanup_complete"]
        assert plan["reserved_seconds"] == 60
        assert (
            client.call("environment_build", operation_id="build", plan_id=pid, revision=1)[
                "attempts"
            ][0]["attempt_id"]
            == attempt["attempt_id"]
        )
        with pytest.raises(ValueError, match="budget exhausted"):
            client.call("environment_build", operation_id="new-build", plan_id=pid, revision=1)
        run = client.call(
            "open",
            operation_id="after-recovery",
            image="python:3.12-slim",
            memory_bytes=256 * 1024**2,
        )
        client.call("close", operation_id="close", run_id=run["run_id"])
