"""Research analysis tools; authorizations are recorded explicitly through the operator CLI."""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent_infra.gateways.cli.research_runtime import ResearchClient


def add_study_tools(server: FastMCP, client: ResearchClient) -> None:
    @server.tool()
    def analysis_save(document: dict[str, Any], operation_id: str) -> dict[str, Any]:
        """Save interpretation with real Run/artifact/JSON metric references."""
        return client.call("study_analysis_save", operation_id=operation_id, document=document)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def analysis_list() -> dict[str, Any]:
        """Read prior immutable analyses and their evidence."""
        return client.call("study_analyses")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def iteration_workflows() -> dict[str, Any]:
        """Read user-authorized task sets, limits and durable workflow IDs."""
        return client.call("study_workflows")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def iteration_status(workflow_id: str) -> dict[str, Any]:
        """Resume from durable action IDs and Run states. Never auto-replays execution."""
        return client.call("study_status", workflow_id=workflow_id)

    @server.tool()
    def iteration_step(workflow_id: str, task_key: str, operation_id: str) -> dict[str, Any]:
        """Submit one preauthorized frozen Task within remaining budget; retry with the same ID."""
        return client.call(
            "study_step", operation_id=operation_id, workflow_id=workflow_id, task_key=task_key
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def iteration_read(
        workflow_id: str, run_id: str, artifact_id: str | None = None, member: str | None = None
    ) -> dict[str, Any]:
        """Read workflow Run status/artifacts; exact member bytes are returned as base64."""
        return client.call(
            "study_read",
            workflow_id=workflow_id,
            run_id=run_id,
            artifact_id=artifact_id,
            member=member,
        )
