"""Workspace checks use synthetic persisted evidence; no execution backend is invoked."""

import copy
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from agent_infra.bootstrap.benchmark_console import BenchmarkConsole
from agent_infra.bootstrap.benchmark_workspace import BenchmarkWorkspace
from agent_infra.gateways.http.server import create_server
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.benchmark_views import compare_runs


# Fixture module is loaded explicitly; it is not part of the installed application.
@pytest.fixture
def batches(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "fixtures"))
    from benchmark_workspace import make_batch

    first = make_batch(tmp_path / "baseline", "baseline")
    second = make_batch(tmp_path / "revised", "revised", incomplete=True)
    workspace = BenchmarkWorkspace(tmp_path / "console")
    left = workspace.register({"path": str(first["root"])})["id"]
    right = workspace.register({"path": str(second["root"])})["id"]
    return workspace, left, right, first, second


def test_register_all_members_and_compare_missing_zero_and_invalid(batches):
    workspace, left, right, first, _ = batches
    assert workspace.register({"path": str(first["root"])})["id"] == left
    a, b = workspace.detail(left), workspace.detail(right)
    assert a["total"] == b["total"] == 60
    assert b["runs"][-1]["state"] == "not_submitted"
    assert b["scored"] == 58
    assert a["runs"][0]["metrics"]["score"] == 0
    assert "PRIVATE_NATIVE_SENTINEL" not in json.dumps(workspace.overview())
    assert "PRIVATE_NATIVE_SENTINEL" not in json.dumps(a)
    compared = compare_runs(a["runs"], b["runs"], "score")
    assert compared["paired"] == 58 and compared["mean_delta"] == 2
    assert compared["rows"][-1]["delta"] is None
    altered = copy.deepcopy(b["runs"])
    altered[0]["comparison_key"] = "different protocol"
    assert compare_runs(a["runs"], altered, "score")["paired"] == 57
    assert compare_runs(a["runs"], [*b["runs"], b["runs"][0]], "score")["paired"] == 57


def test_notes_conflicts_baseline_and_registration_integrity(batches):
    workspace, left, right, first, _ = batches
    note = workspace.annotate(left, {"notes": "check math", "name": "Baseline"})
    assert note["revision"] == 1
    with pytest.raises(ValueError, match="刷新"):
        workspace.annotate(left, {"notes": "stale"})
    workspace.annotate(left, {"notes": "task note"}, "task-000")
    assert workspace.detail(left)["runs"][0]["annotation"]["notes"] == "task note"
    with pytest.raises(KeyError):
        workspace.annotate(left, {"notes": "wrong"}, "unknown")
    saved = workspace.route("POST", ["settings"], {}, {"baseline": right})
    assert saved["baseline"] == right
    plan = first["root"] / "batch.json"
    value = json.loads(plan.read_text())
    value["model"] = "changed"
    plan.write_text(json.dumps(value))
    assert workspace.overview()["errors"]


def test_trace_search_entire_archive_and_member_ownership(batches):
    workspace, left, right, first, second = batches
    run = first["runs"][0]
    before = first["store"].get(run["run_id"])
    records_root = first["root"] / "state/benchmarks/records"
    files_before = {
        p.relative_to(records_root): p.stat().st_mtime_ns
        for p in records_root.rglob("*")
        if p.is_file() and p.suffix not in {".sqlite3-shm", ".sqlite3-wal"}
    }
    evidence = workspace.evidence(left, run["run_id"])
    page = evidence.trajectory(search="DEEP_ERROR", kind="errors")
    assert page["matched_steps"] == 1
    assert page["steps"][0]["step_index"] == 57
    assert evidence.trajectory(cursor=100)["steps"][0]["step_index"] == 100
    with pytest.raises(KeyError):
        workspace.evidence(left, second["runs"][0]["run_id"])
    with pytest.raises(KeyError):
        evidence.file("../../batch.json")
    assert evidence.file("outputs/score.json")["size_bytes"] > 0
    assert first["store"].get(run["run_id"]) == before
    assert {
        p.relative_to(records_root): p.stat().st_mtime_ns
        for p in records_root.rglob("*")
        if p.is_file() and p.suffix not in {".sqlite3-shm", ".sqlite3-wal"}
    } == files_before
    assert LocalRecordsStore(records_root, read_only=True).get_run(run["run_id"])


def test_authenticated_http_register_notes_query_and_cancel_intent(batches, tmp_path):
    workspace, left, _, first, _ = batches
    console = BenchmarkConsole(workspace.state)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("fixture")
    token = "test-workspace-token-" * 3
    server = create_server(None, web, token, 0, benchmark=console)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(method, path, body=None, authorized=True):
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + token
        client.request(
            method,
            "/api/v1/benchmarks/workspace" + path,
            json.dumps(body) if body is not None else None,
            headers,
        )
        response = client.getresponse()
        result = response.status, json.loads(response.read())
        client.close()
        return result

    try:
        assert call("GET", "", authorized=False)[0] == 401
        assert call("POST", "/" + left + "/note", {"notes": "saved"})[0] == 200
        assert call("GET", "/" + left)[1]["annotation"]["notes"] == "saved"
        run_id = first["runs"][0]["run_id"]
        first["store"].update(run_id, state="running")
        assert call("POST", f"/{left}/runs/{run_id}/cancel", {})[1]["cancel_requested"]
        assert first["store"].get(run_id)["state"] == "running"
        assert call("GET", f"/{left}/runs/{run_id}/trajectory?kind=bad")[0] == 400
        assert call("POST", "", {"path": "relative"})[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_log_tail_committed_bytes_scope_and_finalization(batches):
    from agent_infra.records.api import CaptureStatus, DataClass, ProducerKind, RecordContext

    workspace, left, _, first, _ = batches
    run = first["runs"][0]
    records = LocalRecordsStore(first["root"] / "state/benchmarks/records")
    sink = records.scoped_sink(
        RecordContext(run["run_id"], run["attempt_id"], "logs", ProducerKind.RUN)
    )
    stream = run["attempt_id"] + ":combined"
    sink.start_stream(stream, "combined")
    sink.append_stream(stream, b"hello log", 0)
    assert workspace.logs(left, run["run_id"])["text"] == "hello log"
    readonly = LocalRecordsStore(records.root, read_only=True)
    assert readonly.read_stream_tail(run["attempt_id"], stream, limit=3).data == b"log"
    with pytest.raises(KeyError):
        readonly.read_stream_tail("wrong-attempt", stream)
    with pytest.raises(ValueError):
        readonly.read_stream_tail(run["attempt_id"], stream, limit=65537)
    sink.finalize_stream(stream, CaptureStatus.COMPLETE)
    assert workspace.logs(left, run["run_id"])["capture_status"] == "complete"
    assert readonly.read_stream_tail(run["attempt_id"], stream).data == b"hello log"
    secret = run["attempt_id"] + ":secret"
    sink.start_stream(secret, "secret", data_class=DataClass.SECRET)


def test_missing_state_reads_do_not_create_runtime_files(tmp_path):
    workspace = BenchmarkWorkspace(tmp_path / "absent")
    assert workspace.overview()["batches"] == []
    assert not workspace.state.exists()


def test_nonfinite_metrics_never_enter_comparisons(batches):
    from agent_infra.runs.benchmark_views import project_run

    _, _, _, first, _ = batches
    item = copy.deepcopy(first["runs"][0])
    item["result"]["native_result"]["metrics"] = {
        "nan": float("nan"),
        "bool": True,
        "inf": float("inf"),
    }
    value = project_run(item)
    assert value["metrics"] == {} and not value["score_valid"]
