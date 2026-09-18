"""No external network: authenticate and tunnel against a local fake upstream."""

import base64
import socket
import socketserver
from threading import Thread
from urllib.parse import urlsplit

import pytest

from agent_infra.environments.model_proxy import ModelProxyRelay, model_connection


def read_header(connection):
    value = b""
    while not value.endswith(b"\r\n\r\n"):
        value += connection.recv(1)
    return value


def test_proxy_auth_target_scope_and_bidirectional_tunnel():
    seen = []

    class Upstream(socketserver.BaseRequestHandler):
        def handle(self):
            header = read_header(self.request)
            seen.append(header)
            self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.request.sendall(self.request.recv(10))

    upstream = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Upstream)
    thread = Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    relay = ModelProxyRelay(upstream.server_address, "127.0.0.1")
    url = urlsplit(relay.url)
    auth = base64.b64encode(f"{url.username}:{url.password}".encode()).decode()
    try:
        for target, token, expected in [
            ("api.openai.com:443", "wrong", b"407"),
            ("127.0.0.1:22", auth, b"403"),
            ("other.example:443", auth, b"403"),
            ("api.openai.com:443", auth, b"200"),
        ]:
            with socket.create_connection((url.hostname, url.port), timeout=3) as client:
                client.sendall(
                    (
                        f"CONNECT {target} HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n"
                    ).encode()
                )
                assert expected in read_header(client)
                if expected == b"200":
                    client.sendall(b"hello")
                    assert client.recv(5) == b"hello"
        assert len(seen) == 1
        assert b"Proxy-Authorization" not in seen[0]
    finally:
        relay.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_direct_does_not_inherit_host_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1234")
    assert model_connection("direct") == ((), None)
    with pytest.raises(ValueError, match="without credentials"):
        model_connection("http://user:password@proxy:1234")
