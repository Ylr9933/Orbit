"""Real CPU Docker with an explicit deterministic fixture; never calls a model."""

import json
import multiprocessing
import subprocess
import time

import pytest

from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.recovery import recover_owned_containers
from agent_infra.records import EventQuery
from agent_infra.runs.host_lock import HostControllerLock
from tests.unit.runs.test_controller import REQUEST, setup_controller, wait_finished

pytestmark = pytest.mark.e2e


def child_controller(root):
    lock = HostControllerLock(root, namespace=root / "host-lock")
    control, _, prepared = setup_controller(root, environment=DockerEnvironment(root / "docker"))
    prepared.agent.code = "import time; print('fixture running', flush=True); time.sleep(180)"
    entry = control.submit("crash-test", REQUEST)
    (root / "accepted.json").write_text(json.dumps(entry))
    try:
        while True:
            time.sleep(0.1)
    finally:
        lock.close(clean=control.close())


def test_sigkill_restart_cleans_only_owned_container_without_replay(tmp_path):
    child = multiprocessing.get_context("fork").Process(target=child_controller, args=(tmp_path,))
    child.start()
    try:
        deadline = time.monotonic() + 30
        name = None
        while time.monotonic() < deadline:
            for path in (tmp_path / "docker").glob("*/ownership.json"):
                name = json.loads(path.read_text())["name"]
                info = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
                if info.returncode == 0 and json.loads(info.stdout)[0]["State"]["Running"]:
                    break
            else:
                time.sleep(0.1)
                continue
            break
        else:
            pytest.fail("owned Docker fixture did not start")
        child.kill()
        child.join(10)
        assert not child.is_alive()
        lock = HostControllerLock(tmp_path, namespace=tmp_path / "host-lock")
        try:
            recovered, _, _ = setup_controller(
                tmp_path,
                environment=DockerEnvironment(tmp_path / "docker"),
                recover=lambda: recover_owned_containers(tmp_path / "docker"),
            )
            entry = json.loads((tmp_path / "accepted.json").read_text())
            result = recovered.store.get(entry["run_id"])
            assert result["result"]["status"] == "interrupted"
            assert result["result"]["cleanup_complete"]
            assert recovered.submit("crash-test", REQUEST)["run_id"] == entry["run_id"]
            assert len(recovered.store.list_runs()) == 1
            assert not recovered.resources.active_leases
            assert subprocess.run(["docker", "inspect", name], capture_output=True).returncode != 0
            assert not (recovered.service.state_dir / entry["run_id"] / "agent-home").exists()
            recovered.close()
        finally:
            lock.close(clean=True)
    finally:
        if child.is_alive():
            child.kill()
            child.join(10)
        recover_owned_containers(tmp_path / "docker")


def test_real_background_cancellation_and_records_after_removal(tmp_path):
    control, _, prepared = setup_controller(
        tmp_path, environment=DockerEnvironment(tmp_path / "docker")
    )
    prepared.agent.code = "import time; print('fixture running', flush=True); time.sleep(120)"
    try:
        entry = control.submit("cancel-real", REQUEST)
        deadline = time.monotonic() + 20
        while not list((tmp_path / "docker").glob("*/ownership.json")):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        control.cancel(entry["run_id"])
        result = wait_finished(control, entry["run_id"])["result"]
        assert result["status"] == "cancelled"
        assert result["cleanup_complete"] and result["lease_released"]
        assert control.records.get_attempt(entry["attempt_id"]).status == "cancelled"
        events = control.records.read_events(EventQuery(attempt_id=entry["attempt_id"])).items
        assert any(
            event.event_type == "process.exited" and event.payload["status"] == "cancelled"
            for event in events
        )
        assert not recover_owned_containers(tmp_path / "docker")
    finally:
        control.close()
        recover_owned_containers(tmp_path / "docker")
