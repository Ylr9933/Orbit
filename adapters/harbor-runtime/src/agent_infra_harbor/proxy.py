"""Task-scoped relay to an operator's loopback HTTP proxy, for public solver networks."""

import asyncio
import ipaddress
import json
from urllib.parse import urlparse

from .docker import docker


def proxy_address(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("proxy_url must be an HTTP loopback proxy without credentials")
    return "127.0.0.1", parsed.port


class SolverProxy:
    def __init__(self, url: str):
        self.upstream = proxy_address(url)
        self.allowed: set[str] = set()
        self.connections: set[asyncio.Task] = set()
        self.server = None
        self.url = ""

    async def start(self) -> None:
        network = json.loads(docker("network", "inspect", "bridge"))[0]
        gateway = str(ipaddress.IPv4Address(network["IPAM"]["Config"][0]["Gateway"]))
        self.server = await asyncio.start_server(self._accept, gateway, 0)
        port = self.server.sockets[0].getsockname()[1]
        self.url = f"http://{gateway}:{port}"

    async def _accept(self, reader, writer) -> None:
        if writer.get_extra_info("peername")[0] not in self.allowed:
            writer.close()
            await writer.wait_closed()
            return
        task = asyncio.current_task()
        self.connections.add(task)
        remote = None
        pumps = []
        try:
            upstream, remote = await asyncio.wait_for(asyncio.open_connection(*self.upstream), 15)

            async def copy(source, destination):
                while block := await source.read(65536):
                    destination.write(block)
                    await destination.drain()

            pumps = [
                asyncio.create_task(copy(reader, remote)),
                asyncio.create_task(copy(upstream, writer)),
            ]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, TimeoutError):
            pass
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for stream in (writer, remote):
                if stream:
                    stream.close()
            self.connections.discard(task)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        pending = list(self.connections)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
