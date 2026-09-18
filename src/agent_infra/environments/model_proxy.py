"""Small authenticated CONNECT relay for a host-loopback model proxy.

TLS stays end to end. The relay accepts only OpenAI model endpoints, never generic
HTTP forwarding or arbitrary host ports. It is owned by the controller process.
"""

import base64
import hmac
import os
import secrets
import select
import socket
import socketserver
import threading
from urllib.parse import urlsplit

from agent_infra.environments.recovery import docker_json


def _header(connection: socket.socket) -> bytes:
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        chunk = connection.recv(1)
        if not chunk or len(data) >= 16384:
            raise ValueError("invalid proxy header")
        data.extend(chunk)
    return bytes(data)


class ModelProxyRelay:
    def __init__(self, upstream: tuple[str, int], bind: str) -> None:
        secret = secrets.token_urlsafe(32)
        authorization = "Basic " + base64.b64encode(("agent:" + secret).encode()).decode()
        self.stop = threading.Event()
        relay = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                client = self.request
                client.settimeout(10)
                try:
                    lines = _header(client).decode("ascii").split("\r\n")
                    method, target, version = lines[0].split()
                    headers = dict(line.split(":", 1) for line in lines[1:] if line)
                    auth = next(
                        (
                            v.strip()
                            for k, v in headers.items()
                            if k.lower() == "proxy-authorization"
                        ),
                        "",
                    )
                    if not hmac.compare_digest(auth, authorization):
                        client.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                        return
                    if method != "CONNECT" or target.lower() not in {
                        "chatgpt.com:443",
                        "api.openai.com:443",
                    }:
                        client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                        return
                    with socket.create_connection(upstream, timeout=10) as remote:
                        remote.sendall(
                            f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode()
                        )
                        response = _header(remote)
                        client.sendall(response)
                        if response.split(b" ", 2)[1] != b"200":
                            return
                        while not relay.stop.is_set():
                            readable, _, _ = select.select([client, remote], [], [], 0.5)
                            for source in readable:
                                data = source.recv(65536)
                                if not data:
                                    return
                                (remote if source is client else client).sendall(data)
                except (OSError, ValueError, UnicodeError):
                    return  # Never log URLs, proxy credentials or TLS bytes.

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            request_queue_size = 16

        self.server = Server((bind, 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="model-proxy-relay"
        )
        self.thread.start()
        self.url = f"http://agent:{secret}@{bind}:{self.server.server_address[1]}"

    def close(self) -> None:
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def model_connection(
    selection: str = "auto",
) -> tuple[tuple[tuple[str, str], ...], ModelProxyRelay | None]:
    value = selection
    if selection == "auto":
        value = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "direct"
    if value == "direct":
        return (), None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or not parsed.port
        or parsed.username
        or parsed.password
    ):
        raise ValueError("model proxy must be an http://host:port URL without credentials")
    relay = None
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        network = docker_json("network", "inspect", "bridge")[0]
        gateway = network["IPAM"]["Config"][0]["Gateway"]
        relay = ModelProxyRelay((parsed.hostname, parsed.port), gateway)
        value = relay.url
    return (("HTTPS_PROXY", value), ("HTTP_PROXY", value)), relay
