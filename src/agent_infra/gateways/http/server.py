"""Loopback-only, bearer-authenticated local console transport."""

import hmac
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, unquote, urlsplit

from agent_infra.gateways.http.workflow import WorkflowGateway
from agent_infra.projects.api import ProjectConflict, ProjectNotFound
from agent_infra.records.catalog import CatalogConflict
from agent_infra.runs.console import ConsoleService


class BenchmarkView(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def trajectory(self, run_id: str, *, cursor: int = 0, limit: int = 50) -> dict[str, Any]: ...


def create_server(
    service: ConsoleService,
    web_root: Path,
    token: str,
    port: int = 8765,
    *,
    workflow: WorkflowGateway | None = None,
    benchmark: BenchmarkView | None = None,
) -> ThreadingHTTPServer:
    if len(token) < 32:
        raise ValueError("console token must have at least 32 characters")
    root = web_root.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # Never log credentials, URLs or user content.

        def send_body(self, code: int, data: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
                "object-src 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def respond(self, code: int, value: object) -> None:
            self.send_body(
                code,
                json.dumps(value, ensure_ascii=False, default=str).encode(),
                "application/json",
            )

        def allowed_host(self) -> bool:
            port = cast(ThreadingHTTPServer, self.server).server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def authorized(self) -> bool:
            provided = self.headers.get("Authorization", "").encode()
            return hmac.compare_digest(provided, ("Bearer " + token).encode())

        def do_GET(self) -> None:
            self.dispatch("GET")

        def do_POST(self) -> None:
            self.dispatch("POST")

        def dispatch(self, method: str) -> None:
            if not self.allowed_host():
                self.respond(403, {"error": "Host 不允许"})
                return
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if path.startswith("/api/"):
                if not self.authorized():
                    self.respond(401, {"error": "请输入本机控制台访问令牌"})
                    return
                try:
                    query = parse_qs(parsed.query)
                    result = self.api(method, path, query)
                    self.respond(200, result)
                except (CatalogConflict, ProjectConflict) as error:
                    self.respond(409, {"error": str(error)})
                except (KeyError, ProjectNotFound):
                    self.respond(404, {"error": "未找到请求的记录"})
                except (ValueError, TypeError) as error:
                    self.respond(400, {"error": str(error)})
                except Exception:
                    self.respond(503, {"error": "服务暂不可用；请检查本机状态目录"})
                return
            if method != "GET":
                self.respond(405, {"error": "方法不支持"})
                return
            target = (root / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                self.respond(404, {"error": "页面不存在；请先构建 Web"})
                return
            # Only the explicitly configured build output can be served.
            self.send_body(
                200, target.read_bytes(), mimetypes.guess_type(target)[0] or "text/plain"
            )

        def api(self, method: str, path: str, query: dict[str, list[str]]) -> object:
            body: dict[str, Any] = {}
            if method == "POST":
                if workflow is None and path != "/api/v1/projects":
                    raise KeyError(path)
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("expected JSON")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("invalid body size")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("expected object")
            parts = path.removeprefix("/api/v1/").split("/")
            if method == "GET" and path == "/api/v1/benchmarks":
                if benchmark is None:
                    raise KeyError(path)
                return benchmark.snapshot()
            if method == "GET" and len(parts) == 3 and parts[:2] == ["benchmarks", "runs"]:
                if benchmark is None:
                    raise KeyError(path)
                return benchmark.trajectory(
                    parts[2],
                    cursor=int(query.get("cursor", ["0"])[0]),
                    limit=int(query.get("limit", ["50"])[0]),
                )
            if workflow is not None and (
                parts[0] in {"execution", "capabilities"}
                or (parts[0] == "projects" and (method == "GET" or len(parts) > 1))
            ):
                return workflow.route(method, parts, query, body)
            if method == "POST":
                if path != "/api/v1/projects":
                    raise KeyError(path)
                if workflow is not None and body.get("id") is None:
                    raise ValueError("请使用项目初始化入口创建工作区")
                return service.save_project(body)
            if path == "/api/v1/capabilities":
                return {
                    "scope": "local_administrator",
                    "run_control": False,
                    "live_agent_trace": False,
                    "artifact_download": False,
                }
            if path == "/api/v1/resources":
                return service.resources()
            if path == "/api/v1/agents":
                return {"items": service.agents()}
            if path == "/api/v1/tasks":
                return {"items": service.tasks()}
            if path == "/api/v1/projects":
                return {"items": service.catalog.list_projects()}
            if path == "/api/v1/runs":
                return service.runs(int(query.get("offset", ["0"])[0]))
            parts = path.split("/")
            if len(parts) == 5 and parts[1:4] == ["api", "v1", "runs"]:
                return service.run_detail(parts[4])
            if len(parts) == 6 and parts[1:4] == ["api", "v1", "attempts"]:
                if parts[5] == "events":
                    return service.events(parts[4], query.get("cursor", [None])[0])
                if parts[5] == "artifacts":
                    return {"items": service.artifacts(parts[4])}
            raise KeyError(path)

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def get_request(self) -> Any:
            connection, address = super().get_request()
            connection.settimeout(10)
            return connection, address

    return Server(("127.0.0.1", port), Handler)
