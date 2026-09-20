"""Add bounded environment preparation tools without owning execution in MCP."""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent_infra.gateways.cli.research_runtime import ResearchClient


def add_environment_tools(server: FastMCP, client: ResearchClient) -> None:
    @server.tool()
    def environment_plan(intent: dict[str, Any], operation_id: str) -> dict[str, Any]:
        """Save USER-AUTHORIZED intent/budget before proposing dependencies.

        Required: goal, base_image (existing local Python 3 image).
        Optional: template python-cpu/existing, imports, allowed_packages, agent none/codex,
        network false, cpu 1, memory_bytes 2147483648, max_attempts 3,
        total_seconds 600, attempt_seconds 180, valid_seconds 86400.
        Keep imports, base, network and resource budget fixed during repairs.
        Never create another plan to bypass an exhausted user budget.
        """
        return client.call("environment_plan", operation_id=operation_id, intent=intent)

    @server.tool()
    def environment_propose(
        plan_id: str,
        expected_revision: int,
        dependencies: list[str],
        reason: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Propose exact public wheel requirements, e.g. numpy==2.2.6; source is agent.

        For repairs read failed attempt logs, add/fix only allowed dependencies and
        explain the evidence in reason. Cannot weaken smoke or expand permissions.
        Next call environment_build with the returned current revision.
        """
        return client.call(
            "environment_propose",
            operation_id=operation_id,
            plan_id=plan_id,
            expected_revision=expected_revision,
            proposal={"dependencies": dependencies, "source": "agent", "reason": reason},
        )

    @server.tool()
    def environment_build(plan_id: str, revision: int, operation_id: str) -> dict[str, Any]:
        """Start one bounded build+fresh smoke asynchronously; poll environment_plan_status.

        Failure is evidence, not readiness. Revise only within the original budget.
        Exhaustion requires a new USER decision; do not loop or replace the plan.
        """
        return client.call(
            "environment_build", operation_id=operation_id, plan_id=plan_id, revision=revision
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def environment_plan_status(
        plan_id: str, attempt_id: str | None = None, cursor: int = 0
    ) -> dict[str, Any]:
        """Read versions, spent budget, attempt results and validated lock; optional paged logs."""
        return client.call(
            "environment_status", plan_id=plan_id, attempt_id=attempt_id, cursor=cursor
        )

    @server.tool()
    def environment_cancel(plan_id: str, operation_id: str) -> dict[str, Any]:
        """Request cancellation; poll until cleanup_complete before starting another job."""
        return client.call("environment_cancel", operation_id=operation_id, plan_id=plan_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def environment_plans() -> dict[str, Any]:
        """List this project's environment plans and repair history for session recovery."""
        return client.call("environment_list")
