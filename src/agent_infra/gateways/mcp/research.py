"""Project-scoped stdio tools. Controller, not MCP, owns all execution state."""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent_infra.gateways.cli.research_runtime import ResearchClient


def create_mcp(client: ResearchClient) -> FastMCP:
    server = FastMCP(
        "agent-infra-research",
        instructions=(
            "Tools are bound to one project. Use stable operation IDs for retries. "
            "Jobs run in /workspace of a CPU Docker image. Disconnecting does not stop "
            "Jobs; explicitly close the environment to release resources. No host shell."
        ),
    )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def project_context() -> dict[str, Any]:
        """Read goal, adopted research plan and existing research Runs before acting."""
        return client.call("context")

    @server.tool()
    def environment_open(
        image: str, operation_id: str, cpu: float = 1, memory_gib: float = 2
    ) -> dict[str, Any]:
        """Start a persistent Python 3 environment with CPU/memory limits and no network."""
        return client.call(
            "open",
            operation_id=operation_id,
            image=image,
            cpu=cpu,
            memory_bytes=int(memory_gib * 1024**3),
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def environment_status(run_id: str) -> dict[str, Any]:
        """Inspect the environment and all Jobs; safe after reconnect or completion."""
        return client.call("status", run_id=run_id)

    @server.tool()
    def environment_close(run_id: str, operation_id: str) -> dict[str, Any]:
        """Stop all Jobs, remove container, freeze/archive workspace and release resources."""
        return client.call("close", operation_id=operation_id, run_id=run_id)

    @server.tool()
    def job_start(
        run_id: str,
        argv: list[str],
        operation_id: str,
        cwd: str = ".",
        timeout_seconds: float = 3600,
    ) -> dict[str, Any]:
        """Start a background command (argv, no implicit shell); one active Job per environment."""
        return client.call(
            "start",
            operation_id=operation_id,
            run_id=run_id,
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def job_logs(run_id: str, job_id: str, cursor: int = 0) -> dict[str, Any]:
        """Read merged stdout/stderr and Job state; reuse next_cursor for incremental logs."""
        return client.call("logs", run_id=run_id, job_id=job_id, cursor=cursor)

    @server.tool()
    def job_stop(run_id: str, job_id: str, operation_id: str) -> dict[str, Any]:
        """Stop the Job process group; keep the environment for further experiments."""
        return client.call("stop", operation_id=operation_id, run_id=run_id, job_id=job_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def workspace_read(run_id: str, path: str, offset: int = 0) -> dict[str, Any]:
        """Read up to 64 KiB of a relative workspace file, with byte offset and EOF."""
        return client.call("read", run_id=run_id, path=path, offset=offset)

    @server.tool()
    def workspace_write(run_id: str, path: str, text: str, operation_id: str) -> dict[str, Any]:
        """Write a UTF-8 file up to 32 KiB; create parents inside workspace."""
        return client.call("write", operation_id=operation_id, run_id=run_id, path=path, text=text)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def workspace_list(run_id: str, path: str = ".") -> dict[str, Any]:
        """List up to 200 directory entries in the container workspace."""
        return client.call("list", run_id=run_id, path=path)

    @server.tool()
    def artifact_save(run_id: str, path: str, operation_id: str) -> dict[str, Any]:
        """Snapshot a file (max 16 MiB) into Records; stop writers first."""
        return client.call("archive", operation_id=operation_id, run_id=run_id, path=path)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def artifacts_list(run_id: str) -> dict[str, Any]:
        """List durable artifacts even after the environment has been removed."""
        return client.call("artifacts", run_id=run_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def artifact_read(run_id: str, artifact_id: str, member: str | None = None) -> dict[str, Any]:
        """List artifact members or read an exact member as base64 (max 16 MiB)."""
        return client.call("artifact", run_id=run_id, artifact_id=artifact_id, member=member)

    return server


def serve_mcp(state: Path, project_id: str, session_id: str) -> None:
    create_mcp(ResearchClient(state, project_id, session_id)).run(transport="stdio")
