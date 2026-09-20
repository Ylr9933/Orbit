"""Real local CPU Docker + research controller. Deterministic code, no model."""

import base64
import json
import time

import pytest

from agent_infra.bootstrap.host_research import import_host_trace
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.recovery import inspect_local_image, recover_owned_containers
from agent_infra.environments.research import DockerResearchEnvironment
from agent_infra.runs.research import ResearchController
from agent_infra.runs.research_store import ResearchStore
from tests.unit.runs.test_controller import REQUEST, setup_controller

pytestmark = pytest.mark.e2e


def setup_research(root):
    control, _, _ = setup_controller(
        root, recover=lambda: recover_owned_containers(root / "docker")
    )
    research = ResearchController(
        control,
        ResearchStore(root / "controller"),
        DockerResearchEnvironment(DockerEnvironment(root / "docker")),
        control.records,
        lambda p: {"project": {"project_id": p, "goal": "CPU research"}},
        inspect_local_image,
        import_host_trace,
    )
    return control, research


def completed(research, token, run_id, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = research.call(token, "logs", {"run_id": run_id, "job_id": job_id})
        if response["state"] not in {"accepted", "running"}:
            return response
        time.sleep(0.1)
    pytest.fail("Job did not finish")


def test_research_jobs_isolation_records_and_cleanup(tmp_path):
    control, research = setup_research(tmp_path)
    token = research.bind("project", "session")["binding"]
    other = research.bind("other", "session")["binding"]

    def call(action, op=None, **options):
        result = research.call(token, action, options, op)
        assert "error" not in result, result
        return result

    try:
        options = {"image": "python:3.12-slim", "memory_bytes": 256 * 1024**2}
        run = call("open", "open", **options)
        run_id = run["run_id"]
        assert call("open", "open", **options)["run_id"] == run_id
        with pytest.raises(KeyError):
            research.call(other, "status", {"run_id": run_id})
        with pytest.raises(ValueError, match="already active"):
            control.submit("one-shot-overlap", REQUEST)
        call(
            "write",
            "code",
            run_id=run_id,
            path="code/train.py",
            text=(
                'import json\nprint("hello",flush=True)\n'
                'open("metrics.json","w").write(json.dumps({"score": 3}))\n'
            ),
        )
        job = call("start", "job", run_id=run_id, argv=["python3", "code/train.py"])
        logs = completed(research, token, run_id, job["job_id"])
        assert logs["state"] == "completed" and "hello" in logs["text"]
        assert (
            call("logs", run_id=run_id, job_id=job["job_id"], cursor=logs["next_cursor"])["text"]
            == ""
        )
        artifact = call("archive", "metrics", run_id=run_id, path="metrics.json")
        assert json.loads(call("read", run_id=run_id, path="metrics.json")["text"])["score"] == 3
        assert control.resources.active_leases
        second = research.bind("project", "reconnected")["binding"]
        research.call(second, "status", {"run_id": run_id})
        closed = call("close", "close", run_id=run_id)
        assert closed["result"]["cleanup_complete"] and closed["result"]["archive_complete"], closed
        assert not control.resources.active_leases
        assert len(call("artifacts", run_id=run_id)["items"]) == 2
        manifest = call("artifact", run_id=run_id, artifact_id=artifact["artifact_id"])
        saved = call(
            "artifact",
            run_id=run_id,
            artifact_id=artifact["artifact_id"],
            member=manifest["files"][0]["path"],
        )
        assert json.loads(base64.b64decode(saved["content_base64"]))["score"] == 3
    finally:
        research.close()
        control.close()
        recover_owned_containers(tmp_path / "docker")


def test_stop_timeout_symlink_and_native_import(tmp_path):
    control, research = setup_research(tmp_path)
    token = research.bind("project", "session")["binding"]
    run = research.call(
        token, "open", {"image": "python:3.12-slim", "memory_bytes": 256 * 1024**2}, "open"
    )
    run_id = run["run_id"]
    try:
        job = research.call(
            token, "start", {"run_id": run_id, "argv": ["sh", "-c", "sleep 100 & wait"]}, "long"
        )
        assert (
            research.call(token, "stop", {"run_id": run_id, "job_id": job["job_id"]}, "stop")[
                "state"
            ]
            == "cancelled"
        )
        timeout = research.call(
            token,
            "start",
            {
                "run_id": run_id,
                "argv": ["python3", "-c", "import time; time.sleep(50)"],
                "timeout_seconds": 0.15,
            },
            "timeout",
        )
        assert completed(research, token, run_id, timeout["job_id"])["state"] == "timed_out"
        link = research.call(
            token,
            "start",
            {"run_id": run_id, "argv": ["ln", "-s", "/etc/passwd", "escape"]},
            "link",
        )
        completed(research, token, run_id, link["job_id"])
        assert "error" in research.call(token, "read", {"run_id": run_id, "path": "escape"})
        assert "error" in research.call(
            token, "write", {"run_id": run_id, "path": "../escape", "text": "bad"}, "badwrite"
        )
        remove = research.call(
            token, "start", {"run_id": run_id, "argv": ["rm", "escape"]}, "unlink"
        )
        completed(research, token, run_id, remove["job_id"])
        payload = {
            "run_id": run_id,
            "provider": "codex",
            "source_id": "fixture-trace",
            "text": json.dumps(
                {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}
            ),
        }
        assert "error" not in research.call(token, "import_trace", payload, "import1")
        assert "error" not in research.call(token, "import_trace", payload, "import2")
        events = control.records.read_trace(run["attempt_id"]).events
        assert len([e for e in events if e.event_type == "agent.message"]) == 1
        assert all(
            e.context.producer_kind == "agent" for e in events if e.event_type == "agent.message"
        )
    finally:
        research.close()
        control.close()
        recover_owned_containers(tmp_path / "docker")
