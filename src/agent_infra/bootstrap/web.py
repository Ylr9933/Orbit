"""Composition and lifecycle for the simple local console."""

import secrets
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any

from agent_infra.agents import AgentRegistry
from agent_infra.gateways.http.server import create_server
from agent_infra.records.catalog import LocalProjectCatalog
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources.monitor import LinuxHostResourceMonitor
from agent_infra.resources.sampling import ResourceSampler
from agent_infra.runs.console import ConsoleService


class AgentDiagnostics:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self._lock = Lock()
        self._updated = 0.0
        self._cached: list[dict[str, Any]] = []

    def read(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._cached and monotonic() - self._updated < 60:
                return self._cached
            items = []
            for provider in self.registry.providers:
                agent = self.registry.get(provider)
                item: dict[str, Any] = {
                    "provider": provider,
                    "name": agent.descriptor.display_name,
                    "capabilities": sorted(agent.descriptor.capabilities),
                    "checked_at": datetime.now(UTC).isoformat(),
                }
                try:
                    probe = asdict(agent.probe())
                    item.update(
                        {
                            key: probe[key]
                            for key in (
                                "available",
                                "version",
                                "authenticated",
                                "compatible",
                                "container_auth_reusable",
                                "issues",
                            )
                        }
                    )
                except Exception:
                    item.update(available=None, authenticated=None, issues=["探测失败"])
                items.append(item)
            self._cached, self._updated = items, monotonic()
            return items


def serve_console(
    registry: AgentRegistry,
    records_root: Path,
    console_dir: Path,
    web_root: Path,
    task_paths: tuple[Path, ...],
    port: int,
) -> int:
    if not (web_root / "index.html").is_file():
        raise ValueError("Web 构建不存在，请先执行 pnpm build 并设置 --web-root")
    sampler = ResourceSampler(LinuxHostResourceMonitor().sample)
    service = ConsoleService(
        LocalRecordsStore(records_root),
        LocalProjectCatalog(console_dir / "projects.sqlite3"),
        sampler.read,
        AgentDiagnostics(registry).read,
        task_paths,
    )
    token = secrets.token_urlsafe(32)
    server = create_server(service, web_root, token, port)
    sampler.start()
    print(f"Local console: http://127.0.0.1:{server.server_port}/#token={token}", flush=True)
    print("仅本机管理员访问；令牌随服务重启失效。Ctrl+C 退出。", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        sampler.close()
    return 0
