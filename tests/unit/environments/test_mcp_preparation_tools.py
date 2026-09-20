"""The public tool catalog must distinguish Run status from preparation-plan status."""

import asyncio

from agent_infra.gateways.mcp.research import create_mcp


def test_preparation_tools_do_not_shadow_existing_research_tools():
    server = create_mcp(None)  # Tool catalog inspection does not execute the client.
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert len(tools) == 19
    assert tools["environment_status"].inputSchema["required"] == ["run_id"]
    assert tools["environment_plan_status"].inputSchema["required"] == ["plan_id"]
