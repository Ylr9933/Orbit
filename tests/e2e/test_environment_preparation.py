"""Real local CPU template builds and fresh smoke. No model or GPU calls."""

import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from threading import Event

import pytest

from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.preparation_api import EnvironmentIntent, EnvironmentProposal
from agent_infra.environments.preparation_docker import DockerEnvironmentPreparer
from agent_infra.environments.preparation_store import EnvironmentCatalog
from agent_infra.environments.recovery import docker_json, recover_owned_containers
from agent_infra.resources.api import HostResourceSnapshot
from agent_infra.runs.environment_preparation import EnvironmentPreparation
from tests.unit.runs.test_controller import setup_controller

pytestmark = pytest.mark.e2e


def proposal(dependencies=()):
    return {"dependencies": list(dependencies), "source": "user", "reason": "CPU acceptance"}


def wait_plan(service, project, identifier):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        plan = service.call(project, "session", "environment_status", {"plan_id": identifier}, None)
        if plan["attempts"][-1]["status"] != "running":
            return plan
        time.sleep(0.1)
    pytest.fail("environment preparation did not finish in 120s")


def test_build_repair_cache_lock_and_budget(tmp_path):
    control, _, _ = setup_controller(tmp_path)
    # Preserve the explicitly fake capacity fixture, refreshing only its timestamp.
    control.refresh = lambda: control.resources.update_snapshot(
        HostResourceSnapshot("local", datetime.now(UTC), 1, 0, 0, 512 * 1024**2, 512 * 1024**2)
    )
    backend = DockerEnvironmentPreparer(DockerEnvironment(tmp_path / "docker"))
    service = EnvironmentPreparation(control, EnvironmentCatalog(tmp_path / "preparation"), backend)
    images = set()

    def call(action, **options):
        return service.call(
            "project",
            "session",
            "environment_" + action,
            options,
            "owned-plan" if action == "plan" else uuid.uuid4().hex,
        )

    try:
        call(
            "plan",
            intent={
                "goal": "repair a missing dependency",
                "base_image": "python:3.12-slim",
                "imports": ["six"],
                "allowed_packages": ["six"],
                "network": True,
                "memory_bytes": 256 * 1024**2,
                "max_attempts": 3,
                "attempt_seconds": 60,
            },
        )
        call("propose", plan_id="owned-plan", expected_revision=0, proposal=proposal())
        call("build", plan_id="owned-plan", revision=1)
        first = wait_plan(service, "project", "owned-plan")
        attempt = first["attempts"][-1]
        images.add(attempt["image_id"])
        assert attempt["status"] == "failed", first
        assert attempt["cleanup_complete"] and not attempt["lock"]
        logs = call("status", plan_id="owned-plan", attempt_id=attempt["attempt_id"])["log"]
        assert "ModuleNotFoundError" in logs
        call(
            "propose", plan_id="owned-plan", expected_revision=1, proposal=proposal(["six==1.17.0"])
        )
        call("build", plan_id="owned-plan", revision=2)
        second = wait_plan(service, "project", "owned-plan")
        ready = second["attempts"][-1]
        images.add(ready["image_id"])
        assert ready["status"] == "ready", json.dumps(second)
        lock = ready["lock"]["lock_id"]
        assert service.resolve("project", lock)["image_id"] == ready["image_id"]
        with pytest.raises(KeyError):
            service.resolve("other", lock)
        with pytest.raises(ValueError, match="agent"):
            service.resolve("project", lock, agent="codex")
        # Same pinned input reuses image, but runs another independent smoke.
        call("build", plan_id="owned-plan", revision=2)
        third = wait_plan(service, "project", "owned-plan")
        assert third["attempts"][-1]["details"]["cache_hit"]
        assert third["attempts"][-1]["status"] == "ready"
        with pytest.raises(ValueError, match="budget exhausted"):
            call("build", plan_id="owned-plan", revision=2)
        call("propose", plan_id="owned-plan", expected_revision=2, proposal=proposal())
        with pytest.raises(ValueError, match="proposal changed"):
            service.resolve("project", lock)
        assert not control.resources.active_leases
    finally:
        service.close()
        control.close()
        recover_owned_containers(tmp_path / "docker")
        for image in images - {None}:
            subprocess.run(["docker", "image", "rm", image], check=True, capture_output=True)


def test_existing_codex_layer_and_cancel_timeout(tmp_path):
    backend = DockerEnvironmentPreparer(DockerEnvironment(tmp_path / "docker"))
    intent = EnvironmentIntent.from_dict(
        {
            "goal": "CPU image smoke",
            "base_image": "agent-infra/codex-research:0.154.0",
            "template": "existing",
            "agent": "codex",
            "imports": ["json"],
            "memory_bytes": 256 * 1024**2,
        }
    )
    selected = EnvironmentProposal.from_dict(proposal(), intent)
    base = backend.resolve(intent.base_image, intent.agent)
    images_before = docker_json("image", "inspect", base)[0]["Id"]
    try:
        for name, timeout, cancelled, expected in [
            ("ok", 30, False, "ready"),
            ("cancel", 30, True, "cancelled"),
            ("timeout", 0.00001, False, "timed_out"),
        ]:
            event = Event()
            if cancelled:
                event.set()
            result = backend.execute(
                key="a" * 64,
                intent=intent,
                proposal=selected,
                base=base,
                cached=None,
                workspace=tmp_path / name,
                timeout=timeout,
                cancel=event,
                emit=lambda *_: None,
            )
            assert result.status == expected, result
            assert result.cleanup_complete
        assert docker_json("image", "inspect", base)[0]["Id"] == images_before
    finally:
        recover_owned_containers(tmp_path / "docker")


@pytest.mark.parametrize("cancelled", [True, False])
def test_running_template_cancel_or_timeout_cleans_processes(tmp_path, monkeypatch, cancelled):
    from agent_infra.environments import preparation_docker

    # Deterministic long template fixture, real container/process/cleanup (not an LLM).
    monkeypatch.setattr(
        preparation_docker, "_INSTALL", "import time; print('started',flush=True); time.sleep(120)"
    )
    backend = DockerEnvironmentPreparer(DockerEnvironment(tmp_path / "docker"))
    intent = EnvironmentIntent.from_dict(
        {"goal": "cancellation", "base_image": "python:3.12-slim", "memory_bytes": 256 * 1024**2}
    )
    selected = EnvironmentProposal.from_dict(proposal(), intent)
    cancel = Event()
    seen = []

    def emit(event, payload):
        seen.append(event)
        if cancelled and event == "build.output":
            cancel.set()

    result = backend.execute(
        key="b" * 64,
        intent=intent,
        proposal=selected,
        base=backend.resolve(intent.base_image),
        cached=None,
        workspace=tmp_path / "attempt",
        timeout=30 if cancelled else 2,
        cancel=cancel,
        emit=emit,
    )
    assert "build.started" in seen
    assert result.status == ("cancelled" if cancelled else "timed_out")
    assert result.cleanup_complete and result.image_id is None
    assert all(
        json.loads(p.read_text())["lifecycle"] == "removed"
        for p in (tmp_path / "docker").glob("*/ownership.json")
    )
