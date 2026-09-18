"""Durability, concurrency, cancellation and scoped queries with explicit fake execution."""

import base64
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from agent_infra.gateways.http.control import create_control_server
from agent_infra.records import AttemptManifest, DataClass, ProducerKind, RecordContext, RunManifest
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources import load_resource_request
from agent_infra.runs.api import RunRequest
from agent_infra.runs.control_api import ControlError, PreparedRun, SubmissionRequest
from agent_infra.runs.control_store import RunControlStore
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.host_lock import HostControllerLock
from agent_infra.runs.query import RunQueries
from agent_infra.runs.service import LocalRunService
from agent_infra.tasks import freeze_task, load_task
from tests.unit.runs.test_service import FakeEnvironment, TraceFixtureAgent, manager, setup_task


class CredentialFixture(TraceFixtureAgent):
    def stage_container_credentials(self, destination):
        destination.mkdir(parents=True)
        return destination


REQUEST = SubmissionRequest("test-task", "revision", "explicit-fixture", provider="fixture")


def setup_controller(root, *, environment=None, recover=lambda: None):
    root.mkdir(exist_ok=True)
    request = (
        RunRequest(
            root / "task/task.yaml", root / "resources.yaml", "python:3.12-slim", timeout_seconds=15
        )
        if (root / "task/task.yaml").exists()
        else setup_task(root, evaluation=False)
    )
    request = replace(request, expected_snapshot=freeze_task(load_task(request.task_manifest)))
    env = environment or FakeEnvironment(stdout="fixture trace")
    resources = manager()
    records = LocalRecordsStore(root / "records")
    service = LocalRunService(env, resources, root / "work", node_id="local", records=records)
    prepared = PreparedRun(
        request,
        load_resource_request(request.resource_file),
        CredentialFixture(),
        {"project_id": "project", "experiment_id": "experiment"},
    )
    controller = LocalRunController(
        RunControlStore(root / "controller"),
        service,
        records,
        resources,
        lambda _: prepared,
        lambda: None,
        recover,
    )
    return controller, env, prepared


def wait_finished(controller, run_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        entry = controller.store.get(run_id)
        if entry["state"] in {"finished", "quarantined"}:
            return entry
        time.sleep(0.02)
    pytest.fail("controller did not finish")


def test_preflight_does_not_allocate_or_prepare(tmp_path):
    control, env, prepared = setup_controller(tmp_path)
    try:
        assert control.preflight(REQUEST)["ready"]
        assert not env.specs and not control.resources.active_leases
        assert not control.store.list_runs()
        oversized = replace(prepared, resources=replace(prepared.resources, cpu_cores=2))
        control.prepare = lambda _: oversized
        assert not control.preflight(REQUEST)["ready"]
        with pytest.raises(ControlError, match="authorized"):
            control.submit("large", REQUEST)
        assert not control.store.list_runs()
    finally:
        control.close()


def test_concurrent_retries_single_execution_and_new_operation_reruns(tmp_path):
    control, _, _ = setup_controller(tmp_path)
    try:
        with ThreadPoolExecutor(8) as pool:
            entries = list(pool.map(lambda _: control.submit("same", REQUEST), range(12)))
        identifiers = {entry["run_id"] for entry in entries}
        assert len(identifiers) == 1
        first = wait_finished(control, entries[0]["run_id"])
        assert first["result"]["status"] == "completed"
        assert first["result"]["cleanup_complete"] and first["result"]["lease_released"]
        assert len(control.records.list_attempts(first["run_id"])) == 1
        with pytest.raises(ControlError, match="different parameters"):
            control.submit("same", replace(REQUEST, model="different"))
        second = control.submit("new", REQUEST)
        assert second["run_id"] != first["run_id"]
        wait_finished(control, second["run_id"])
        assert len(control.store.list_runs(project_id="project")) == 2
        reopened = RunControlStore(control.store.path.parent)
        assert reopened.lookup("same", asdict(REQUEST))["run_id"] == first["run_id"]
    finally:
        assert control.close()


def test_busy_cancel_intent_and_cleanup_quarantine(tmp_path):
    env = FakeEnvironment(outcome="running", cleanup=False)
    control, _, _ = setup_controller(tmp_path, environment=env)
    try:
        entry = control.submit("cancel", REQUEST)
        with pytest.raises(ControlError, match="already active"):
            control.submit("second", REQUEST)
        deadline = time.monotonic() + 3
        while not env.specs and time.monotonic() < deadline:
            time.sleep(0.01)
        cancelled = control.cancel(entry["run_id"])
        assert cancelled["cancel_requested"] and cancelled["result"] is None
        final = wait_finished(control, entry["run_id"])
        assert final["state"] == "quarantined"
        assert not final["result"]["cleanup_complete"]
        assert control.resources.active_leases
        with pytest.raises(ControlError, match="quarantined"):
            control.submit("after", REQUEST)
    finally:
        assert not control.close()


def test_recovery_interrupts_without_replay_and_preserves_intent(tmp_path):
    control, _, _ = setup_controller(tmp_path)
    entry = control.store.create("crashed", asdict(REQUEST), {"project_id": "project"})
    records = control.records
    records.begin_run(RunManifest(entry["run_id"], datetime.now(UTC), {}))
    records.begin_attempt(AttemptManifest(entry["attempt_id"], entry["run_id"], datetime.now(UTC)))
    control.close()
    recovered = LocalRunController(
        control.store,
        control.service,
        records,
        manager(),
        lambda _: pytest.fail("must not resume"),
        lambda: None,
        lambda: None,
    )
    try:
        result = recovered.store.get(entry["run_id"])
        assert result["result"]["status"] == "interrupted"
        assert records.get_attempt(entry["attempt_id"]).status == "interrupted"
        assert recovered.submit("crashed", REQUEST)["run_id"] == entry["run_id"]
        assert not recovered.resources.active_leases
    finally:
        recovered.close()


def test_host_lock_cross_state_and_unclean_restart(tmp_path):
    namespace = tmp_path / "namespace"
    one = HostControllerLock(tmp_path / "one", namespace=namespace)
    with pytest.raises(BlockingIOError):
        HostControllerLock(tmp_path / "two", namespace=namespace)
    one.close(clean=False)
    with pytest.raises(RuntimeError, match="needs recovery"):
        HostControllerLock(tmp_path / "two", namespace=namespace)
    recovered = HostControllerLock(tmp_path / "one", namespace=namespace)
    recovered.close(clean=True)
    two = HostControllerLock(tmp_path / "two", namespace=namespace)
    two.close(clean=True)


def test_controlled_artifacts_survive_work_deletion_and_hide_private(tmp_path):
    control, _, _ = setup_controller(tmp_path)
    try:
        entry = control.submit("artifacts", REQUEST)
        wait_finished(control, entry["run_id"])
        shutil.rmtree(control.service.state_dir / entry["run_id"])
        queries = RunQueries(control.store, control.records)
        artifact = next(
            a for a in queries.artifacts(entry["run_id"]) if a["name"] == "solver-submission"
        )
        run_id, artifact_id = entry["run_id"], artifact["artifact_id"]
        result = queries.artifact(run_id, artifact_id, "result.txt")
        assert base64.b64decode(result["content_base64"]) == b"HELLO TASK\n"
        with pytest.raises(KeyError):
            queries.artifact(run_id, artifact_id, "../../auth.json")
        sink = control.records.scoped_sink(
            RecordContext(run_id, entry["attempt_id"], "private", ProducerKind.EVALUATOR)
        )
        private = sink.commit_artifact(
            tmp_path / "resources.yaml", name="private", data_class=DataClass.PRIVATE_EVALUATION
        )
        with pytest.raises(KeyError):
            queries.artifact(run_id, private.artifact_id)
        assert queries.trajectory(run_id)["run_id"] == run_id
        assert queries.events(run_id)["items"]
    finally:
        control.close()


def test_http_authentication_submit_retry_and_cancel(tmp_path):
    control, _, _ = setup_controller(tmp_path)
    server = create_control_server(control, RunQueries(control.store, control.records), "x" * 32, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/v1/runs"
    try:
        with pytest.raises(HTTPError) as error:
            build_opener(ProxyHandler({})).open(url)
        assert error.value.code == 401
        body = json.dumps(asdict(REQUEST) | {"operation_id": "http"}).encode()
        request = Request(
            url,
            data=body,
            headers={"Authorization": "Bearer " + "x" * 32, "Content-Type": "application/json"},
        )
        with build_opener(ProxyHandler({})).open(request) as response:
            first = json.load(response)
        with build_opener(ProxyHandler({})).open(request) as response:
            assert json.load(response)["run_id"] == first["run_id"]
        wait_finished(control, first["run_id"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        control.close()


def test_frozen_input_changed_before_worker_fails_without_allocation(tmp_path):
    control, env, prepared = setup_controller(tmp_path)
    prepared.request.task_manifest.write_text(
        prepared.request.task_manifest.read_text() + "\n# drift\n"
    )
    # Formatting alone does not change semantic digest; change a material instead.
    task = load_task(prepared.request.task_manifest)
    material = next(item for item in task.materials if item.id == "input")
    (prepared.request.task_manifest.parent / material.source / "input.txt").write_text("changed")
    entry = control.submit("drift", REQUEST)
    try:
        result = wait_finished(control, entry["run_id"])
        assert result["result"]["status"] == "failed"
        assert not env.specs and not control.resources.active_leases
    finally:
        control.close()
