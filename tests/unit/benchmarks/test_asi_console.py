"""Benchmark Web reads only the archived trajectory for the selected Run."""

import json
from datetime import UTC, datetime
from http.client import HTTPConnection
from threading import Thread

import pytest

from agent_infra.bootstrap.benchmark_console import BenchmarkConsole
from agent_infra.gateways.http.server import create_server
from agent_infra.records.api import (
    AttemptManifest,
    ProducerKind,
    RecordContext,
    RunManifest,
    Visibility,
)
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.control_store import RunControlStore


@pytest.mark.parametrize("benchmark", ["ASI-Bench", "terminal-bench-science"])
def test_asi_trajectory_is_scoped_to_the_run_and_paged(tmp_path, benchmark):
    state = tmp_path / "state"
    control = RunControlStore(state / "benchmarks")
    request = {
        "execution": {
            "frozen_plan": {
                "plan": {
                    "suite": {"benchmark": benchmark},
                    "units": [{"native_id": "task__seed31415"}],
                }
            }
        }
    }
    run = control.create("op-1", request, {})
    records = LocalRecordsStore(state / "benchmarks" / "records")
    now = datetime.now(UTC)
    records.begin_run(RunManifest(run["run_id"], now, {}))
    records.begin_attempt(AttemptManifest(run["attempt_id"], run["run_id"], now))
    sink = records.scoped_sink(
        RecordContext(run["run_id"], run["attempt_id"], "test", ProducerKind.RUN)
    )
    source = tmp_path / "artifact"
    view = source / "outputs" / "evidence"
    view.mkdir(parents=True)
    (view / "trajectory-view.json").write_text(
        json.dumps(
            [
                {"step_index": 0, "step_type": "tool_call", "content": "run", "metadata": {}},
                {"step_index": 1, "step_type": "tool_result", "content": "ok", "metadata": {}},
            ]
        )
    )
    artifact = sink.commit_artifact(source, name="native-submission", visibility=Visibility.ADMIN)
    control.update(
        run["run_id"],
        state="finished",
        result={
            "artifact_id": artifact.artifact_id,
            "native_result": {
                "instance_id": "task__seed31415",
                "prompt_level": "b1",
                "evidence": {
                    "capture_status": "complete",
                    "trajectory": {
                        "capture_status": "complete",
                        "session_id": "thread-1",
                        "member": "outputs/evidence/trajectory-view.json",
                    },
                },
            },
        },
    )
    console = BenchmarkConsole(state)
    first = console.trajectory(run["run_id"], limit=1)
    assert first["attempt_id"] == run["attempt_id"]
    assert first["session_id"] == "thread-1"
    assert [step["step_type"] for step in first["steps"]] == ["tool_call"]
    assert first["next_cursor"] == 1
    second = console.trajectory(run["run_id"], cursor=1, limit=1)
    assert second["steps"][0]["content"] == "ok"
    assert second["next_cursor"] is None

    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("ok")
    token = "asi-console-test-token-" * 3
    server = create_server(None, web, token, 0, benchmark=console)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        path = f"/api/v1/benchmarks/runs/{run['run_id']}?cursor=1&limit=1"
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        client.request("GET", path)
        assert client.getresponse().status == 401
        client.close()
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        client.request("GET", path, headers={"Authorization": "Bearer " + token})
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["steps"][0]["content"] == "ok"
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
