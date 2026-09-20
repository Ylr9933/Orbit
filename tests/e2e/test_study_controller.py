"""Public HTTP, CLI and stdio MCP analysis over an actual CPU experiment artifact."""

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


def test_cli_mcp_analysis_of_host_research_run(tmp_path):
    state, project = initialize(tmp_path)
    with daemon(state):
        client = ResearchClient(state, project, "analysis-test")
        run = client.call(
            "open",
            operation_id="open",
            image="python:3.12-slim",
            cpu=0.5,
            memory_bytes=256 * 1024**2,
        )
        rid = run["run_id"]
        try:
            job = client.call(
                "start",
                operation_id="job",
                run_id=rid,
                argv=[
                    "python3",
                    "-c",
                    "import json,statistics; from pathlib import Path; "
                    "Path('metrics.json').write_text(json.dumps({'mean':statistics.mean([1,2,3])}))",
                ],
                timeout_seconds=20,
            )
            deadline = time.monotonic() + 30
            while client.call("logs", run_id=rid, job_id=job["job_id"])["state"] in {
                "accepted",
                "running",
            }:
                assert time.monotonic() < deadline
                time.sleep(0.1)
        finally:
            closed = client.call("close", operation_id="close", run_id=rid)
        artifact = closed["result"]["artifact_id"]
        analysis = {
            "results": [
                {
                    "run_id": rid,
                    "artifact_id": artifact,
                    "member": "metrics.json",
                    "data_version": "inline-v1",
                    "code_version": "stdlib-v1",
                    "metrics": [
                        {
                            "name": "mean",
                            "pointer": "/mean",
                            "unit": "scalar",
                            "direction": "inspect",
                        }
                    ],
                }
            ],
            "observations": "read actual mean",
            "interpretation": "fixture integration only",
            "uncertainty": "three samples",
            "recommendation": "review",
        }
        path = tmp_path / "analysis.json"
        path.write_text(json.dumps(analysis))
        command = [
            CLI,
            "study",
            "analysis-save",
            "--project-id",
            project,
            "--state-dir",
            str(state),
            "--operation-id",
            "cli-analysis",
            "--file",
            str(path),
        ]
        saved = json.loads(subprocess.check_output(command, text=True))
        assert saved["evidence"][0]["metrics"][0]["value"] == 2.0
        assert json.loads(subprocess.check_output(command, text=True)) == saved

        async def read():
            params = StdioServerParameters(
                command=CLI,
                args=[
                    "mcp",
                    "--state-dir",
                    str(state),
                    "--project-id",
                    project,
                    "--session-id",
                    "reader",
                ],
            )
            async with (
                stdio_client(params) as (incoming, outgoing),
                ClientSession(incoming, outgoing) as session,
            ):
                await session.initialize()
                result = await session.call_tool("analysis_list", {})
                assert not result.isError
                assert result.structuredContent["items"][0]["analysis_id"] == saved["analysis_id"]

        asyncio.run(read())
        with pytest.raises(ValueError):
            client.call(
                "study_analysis_save",
                operation_id="bad",
                document=analysis | {"results": [{"run_id": "missing"}]},
            )
