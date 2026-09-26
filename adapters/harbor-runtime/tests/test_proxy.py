"""Local sockets only: no Docker, external network or models."""

import asyncio
import json

import pytest
from agent_infra_harbor import proxy


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:80",
        "http://user:secret@127.0.0.1:80",
        "https://127.0.0.1:80",
        "http://127.0.0.1",
    ],
)
def test_proxy_rejects_remote_or_credentialed_endpoints(url):
    with pytest.raises(ValueError):
        proxy.proxy_address(url)


def test_relay_allows_only_attested_solver_and_closes(monkeypatch):
    monkeypatch.setattr(
        proxy, "docker", lambda *_: json.dumps([{"IPAM": {"Config": [{"Gateway": "127.0.0.1"}]}}])
    )

    async def run():
        async def echo(reader, writer):
            data = await reader.read(1024)
            writer.write(data)
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        relay = proxy.SolverProxy(f"http://127.0.0.1:{upstream.sockets[0].getsockname()[1]}")
        await relay.start()
        port = relay.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        assert await asyncio.wait_for(reader.read(), 2) == b""
        writer.close()
        relay.allowed.add("127.0.0.1")
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"probe")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(5), 2) == b"probe"
        writer.close()
        await relay.close()
        assert not relay.connections
        upstream.close()
        await upstream.wait_closed()

    asyncio.run(run())
