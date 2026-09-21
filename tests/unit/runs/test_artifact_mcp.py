"""MCP protocol → authenticated HTTP → bound controller → real Records.

Only the unused execution backend is a fixture. No Docker or model calls.
"""

import argparse
import asyncio
import base64
import json
from threading import Thread

import pytest
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session

from agent_infra.gateways.cli.research_runtime import (
    ResearchClient,
    add_research_runtime_arguments,
    research_client,
)
from agent_infra.gateways.cli.runs import run_client
from agent_infra.gateways.http.control import create_control_server
from agent_infra.gateways.mcp.research import create_mcp
from agent_infra.records.api import DataClass
from tests.unit.runs.test_artifact_views import seed_artifacts
from tests.unit.runs.test_research_lifecycle import setup

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
)


@pytest.fixture
def api(tmp_path):
    control, _, research, _ = setup(tmp_path)
    run, save = seed_artifacts(tmp_path / "artifacts", control.store, control.records)
    server = create_control_server(control, research.queries, "t" * 32, 0, research=research)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "controller/endpoint.json").write_text(
        json.dumps({"port": server.server_port, "token": "t" * 32})
    )
    client = ResearchClient(tmp_path, "project", "read-test")
    try:
        yield tmp_path, run, save, client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        research.close()
        control.close()


def test_mcp_default_json_paging_and_cli_share_readable_view(api):
    state, run, save, client = api
    data = '{"结果":"成功"}\n'.encode()
    artifact = save(data, "nested/summary.json")

    async def check():
        async with create_connected_server_and_client_session(create_mcp(client)) as session:
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert tools["artifact_read"].inputSchema["properties"]["format"]["default"] == "auto"
            args = {"run_id": run, "artifact_id": artifact, "member": "nested/summary.json"}
            response = await session.call_tool("artifact_read", args)
            assert not response.isError
            result = response.structuredContent
            assert result["text"].encode() == data and result["eof"]
            assert "content_base64" not in response.model_dump_json()
            assert json.loads(response.content[0].text) == result
            # The download reference remains valid on the existing authenticated endpoint.
            download = client.client.request(
                result["download"]["controller_path"][len("/api/v1/") :]
            )
            assert base64.b64decode(download["content_base64"]) == data
            page = await session.call_tool("artifact_read", args | {"limit": 7})
            assert page.structuredContent["truncated"]
            raw = await session.call_tool("artifact_read", args | {"format": "base64"})
            assert base64.b64decode(raw.structuredContent["content_base64"]) == data

    asyncio.run(check())
    parser = argparse.ArgumentParser()
    add_research_runtime_arguments(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        [
            "research",
            "artifact",
            run,
            artifact,
            "--project-id",
            "project",
            "--member",
            "nested/summary.json",
            "--limit",
            "7",
        ]
    )
    result = research_client(state, args)
    assert result["format"] == "text" and result["bytes_read"] <= 7
    output = state / "download.json"
    run_client(
        state,
        argparse.Namespace(
            action="artifact",
            run_id=run,
            artifact_id=artifact,
            member="nested/summary.json",
            output=output,
        ),
    )
    assert output.read_bytes() == data


def test_images_are_native_and_resource_links_are_readable(api):
    _, run, save, client = api
    name = "plots/中文 %25 # ?.png"
    artifact = save(PNG, name)
    binary = save(b"\x00\xffmodel", "weights/model.bin")
    big = save(PNG + b"\x00" * 1024**2, "big.png")
    misleading = save(b"not an image", "misleading.png")

    async def check():
        async with create_connected_server_and_client_session(create_mcp(client)) as session:
            args = {"run_id": run, "artifact_id": artifact, "member": name}
            image = await session.call_tool("artifact_read", args)
            assert not image.isError
            assert [part.type for part in image.content] == ["text", "image"]
            assert base64.b64decode(image.content[1].data) == PNG
            assert image.content[1].mimeType == "image/png"
            assert "content_base64" not in image.structuredContent
            assert "data" not in image.structuredContent
            metadata = await session.call_tool("artifact_read", args | {"format": "metadata"})
            assert [part.type for part in metadata.content] == ["text", "resource_link"]
            restored = await session.read_resource(metadata.content[1].uri)
            assert base64.b64decode(restored.contents[0].blob) == PNG
            assert restored.contents[0].mimeType == "image/png"
            large = await session.call_tool(
                "artifact_read",
                {
                    "run_id": run,
                    "artifact_id": big,
                    "member": "big.png",
                },
            )
            assert [part.type for part in large.content] == ["text", "resource_link"]
            invalid = await session.call_tool(
                "artifact_read",
                {
                    "run_id": run,
                    "artifact_id": misleading,
                    "member": "misleading.png",
                },
            )
            assert invalid.structuredContent["kind"] == "binary"
            assert all(part.type != "image" for part in invalid.content)
            result = await session.call_tool(
                "artifact_read",
                {
                    "run_id": run,
                    "artifact_id": binary,
                    "member": "weights/model.bin",
                },
            )
            assert result.structuredContent["format"] == "metadata"
            restored = await session.read_resource(result.content[1].uri)
            assert base64.b64decode(restored.contents[0].blob) == b"\x00\xffmodel"
            forged = str(result.content[1].uri).replace("/binary/", "/png/")
            with pytest.raises(McpError, match="does not match"):
                await session.read_resource(forged)

    asyncio.run(check())


def test_old_controller_does_not_silently_return_base64(api, monkeypatch):
    _, run, save, client = api
    artifact = save(b"{}")
    monkeypatch.setattr(
        client.client,
        "request",
        lambda *args, **kwargs: {
            "path": "summary.json",
            "size_bytes": 2,
            "content_base64": "e30=",
        },
    )
    with pytest.raises(ValueError, match="restart Controller"):
        client.call(
            "artifact", run_id=run, artifact_id=artifact, member="summary.json", format="auto"
        )


def test_mcp_and_resources_enforce_private_artifact_and_project_scope(api):
    state, run, save, client = api
    artifact = save(b"{}")
    private = save(b"answer", data_class=DataClass.PRIVATE_EVALUATION)

    async def check():
        async with create_connected_server_and_client_session(create_mcp(client)) as session:
            for args in (
                {"artifact_id": private, "member": "summary.json"},
                {"artifact_id": artifact, "member": "../summary.json"},
                {"artifact_id": artifact, "member": "summary.json", "offset": -1},
            ):
                result = await session.call_tool("artifact_read", {"run_id": run} | args)
                assert result.isError
            with pytest.raises(McpError):
                await session.read_resource(
                    f"agent-infra://artifacts/binary/{run}/{private}/summary.json"
                )
        other = ResearchClient(state, "other-project", "other-session")
        async with create_connected_server_and_client_session(create_mcp(other)) as session:
            result = await session.call_tool(
                "artifact_read",
                {
                    "run_id": run,
                    "artifact_id": artifact,
                    "member": "summary.json",
                },
            )
            assert result.isError
            with pytest.raises(McpError):
                await session.read_resource(
                    f"agent-infra://artifacts/binary/{run}/{artifact}/summary.json"
                )

    asyncio.run(check())
