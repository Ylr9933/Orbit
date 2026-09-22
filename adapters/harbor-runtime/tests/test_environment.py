"""Pinned Harbor extension tests; no Docker daemon or model calls."""

import asyncio

import pytest
from agent_infra_harbor import environment
from harbor.environments.docker.docker import DockerEnvironment


def owned():
    env = object.__new__(environment.OwnedDockerEnvironment)
    env.project = "infra_" + "a" * 24 + "__env"
    env.claimed = False
    env.launch_uncertain = False
    return env


def test_namespace_collision_never_cleans_foreign_objects(monkeypatch):
    env = owned()
    monkeypatch.setattr(environment, "remaining", lambda _: ["foreign"])

    async def run():
        with pytest.raises(RuntimeError, match="namespace already exists"):
            await env.start(False)
        assert not env.claimed
        await env.stop(True)  # Must not invoke parent Docker/Compose teardown.

    asyncio.run(run())


def test_cancellation_waits_for_daemon_creation_ack(monkeypatch):
    finished = []

    async def create(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        finished.append(True)

    monkeypatch.setattr(DockerEnvironment, "_run_docker_compose_command", create)
    env = owned()

    async def run():
        operation = asyncio.create_task(env._run_docker_compose_command(["up"]))
        await asyncio.sleep(0.001)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert finished and not env.launch_uncertain

    asyncio.run(run())


def test_unacknowledged_creation_stays_uncertain(monkeypatch):
    original_wait = asyncio.wait_for

    async def pending(self, *args, **kwargs):
        await asyncio.sleep(10)

    async def short_wait(awaitable, timeout):
        return await original_wait(awaitable, 0.01)

    monkeypatch.setattr(DockerEnvironment, "_run_docker_compose_command", pending)
    monkeypatch.setattr(asyncio, "wait_for", short_wait)
    env = owned()

    async def run():
        operation = asyncio.create_task(env._run_docker_compose_command(["up"]))
        await asyncio.sleep(0.001)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert env.launch_uncertain

    asyncio.run(run())


def test_teardown_attempts_all_environments_after_failure(monkeypatch):
    visited = []

    class Fake:
        async def stop(self, delete):
            visited.append(delete)
            raise RuntimeError("unavailable")

    monkeypatch.setattr(environment, "ENVIRONMENTS", [Fake(), Fake()])
    with pytest.raises(ExceptionGroup):
        asyncio.run(environment.close_all())
    assert visited == [True, True]
