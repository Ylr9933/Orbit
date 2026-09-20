"""Web-first startup with real Controller, CPU Docker, Records and analysis; no model."""

import base64
import json
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from http.client import HTTPConnection

import pytest

from agent_infra.gateways.cli.research_runtime import ResearchClient
from tests.e2e.test_research_mcp import CLI, daemon

pytestmark = pytest.mark.e2e


@contextmanager
def web(tmp_path, state):
    assets = tmp_path / "web"
    assets.mkdir()
    (assets / "index.html").write_text("Static fixture; browser assets tested separately")
    log = tmp_path / "web.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                CLI,
                "web",
                "--state-dir",
                str(state),
                "--console-dir",
                str(tmp_path / "catalog"),
                "--web-root",
                str(assets),
                "--port",
                "0",
            ],
            stdout=output,
            stderr=output,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                address = re.search(r"127.0.0.1:(\d+)/#token=(\S+)", log.read_text())
                if address:
                    break
                assert process.poll() is None, log.read_text()
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(0.05)

            def call(path, body=None):
                connection = HTTPConnection("127.0.0.1", int(address[1]), timeout=15)
                try:
                    connection.request(
                        "GET" if body is None else "POST",
                        "/api/v1/" + path,
                        body=None if body is None else json.dumps(body),
                        headers={
                            "Authorization": "Bearer " + address[2],
                            "Content-Type": "application/json",
                        },
                    )
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    assert response.status == 200, result
                    return result
                finally:
                    connection.close()

            yield call
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                process.wait(15)


def test_web_first_real_job_records_and_analysis(tmp_path):
    state = tmp_path / "state"
    with web(tmp_path, state) as call:
        assert not call("capabilities")["run_control"]
        project = call(
            "projects/init",
            {
                "goal": "CPU mean calculation",
                "name": "Integration audit",
                "directory": str(tmp_path / "project"),
                "operation_id": "initialize",
            },
        )["project_id"]
        with daemon(state):
            assert call("capabilities")["run_control"]
            client = ResearchClient(state, project, "web-audit")
            run = client.call(
                "open",
                operation_id="open",
                image="python:3.12-slim",
                cpu=0.5,
                memory_bytes=256 * 1024**2,
            )
            rid = run["run_id"]
            try:
                job = client.call(
                    "start",
                    operation_id="job",
                    run_id=rid,
                    argv=[
                        "python3",
                        "-c",
                        "from pathlib import Path; "
                        "Path('metrics.json').write_text('{\"mean\": 2.0}')",
                    ],
                    timeout_seconds=20,
                )
                deadline = time.monotonic() + 30
                while True:
                    logs = client.call("logs", run_id=rid, job_id=job["job_id"])
                    if logs["state"] not in {"accepted", "running"}:
                        assert logs["exit_code"] == 0, logs
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
            finally:
                closed = client.call("close", operation_id="close", run_id=rid)
            assert closed["result"]["cleanup_complete"] and closed["result"]["lease_released"]
            artifact = closed["result"]["artifact_id"]
            client.call(
                "study_analysis_save",
                operation_id="analysis",
                document={
                    "results": [
                        {
                            "run_id": rid,
                            "artifact_id": artifact,
                            "member": "metrics.json",
                            "data_version": "inline-v1",
                            "code_version": "stdlib-v1",
                            "metrics": [
                                {
                                    "name": "mean",
                                    "pointer": "/mean",
                                    "unit": "scalar",
                                    "direction": "inspect",
                                }
                            ],
                        }
                    ],
                    "observations": "mean equals two",
                    "interpretation": "integration fixture",
                    "uncertainty": "no scientific claim",
                    "recommendation": "review",
                },
            )
            detail = call(f"projects/{project}")
            assert detail["runs"][0]["run_id"] == rid
            assert detail["research"]["run_references"][0]["run_id"] == rid
            assert "request" not in detail["research"]["run_references"][0]
            assert detail["analyses"][0]["evidence"][0]["metrics"][0]["value"] == 2.0
            content = call(f"execution/runs/{rid}/artifacts/{artifact}?member=metrics.json")
            assert json.loads(base64.b64decode(content["content_base64"])) == {"mean": 2.0}
        assert not call("capabilities")["run_control"]
        assert call(f"projects/{project}")["runs"][0]["state"] == "finished"
