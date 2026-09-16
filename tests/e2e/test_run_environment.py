"""Opt-in real local Docker; no model, GPU, network or unrelated container cleanup."""

import json
import time
from dataclasses import replace
from threading import Event

import pytest
import yaml

from agent_infra.environments.api import InputMount, ProcessCommand, SandboxSpec
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.records import EventQuery
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.service import LocalRunService
from tests.unit.runs.test_service import FixtureAgent, manager, recipe, setup_task

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("evaluation", [False, True])
def test_real_run(tmp_path, evaluation):
    request = setup_task(tmp_path, evaluation=evaluation)
    environment = DockerEnvironment(tmp_path / "runtime")
    agent = FixtureAgent(
        "from pathlib import Path; "
        "assert not Path('/inputs/expected').exists(); "
        "assert not Path('/workspace/task.yaml').exists(); "
        "assert not Path('/workspace/private').exists(); "
        "Path('result.txt').write_text(Path('data/input.txt').read_text().upper())"
    )
    result = LocalRunService(
        environment, manager(), tmp_path / "runs", node_id="local", recipes=(recipe(),)
    ).run(request, agent)
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    assert result.status == "completed", (
        result,
        [
            event.event_type
            for event in records.read_events(
                EventQuery(attempt_id=result.attempt_id, limit=500)
            ).items
        ],
    )
    assert result.lease_released and result.cleanup_complete
    assert result.evaluation_status == ("completed" if evaluation else "not_requested")
    if evaluation:
        assert json.loads(result.feedback_json) == {"passed": True}


def test_untrusted_submission_runs_without_answers(tmp_path):
    request = setup_task(tmp_path)
    document = yaml.safe_load(request.task_manifest.read_text())
    document["outputs"]["items"][0]["path"] = "solution.py"
    request.task_manifest.write_text(yaml.safe_dump(document))
    program = (
        "from pathlib import Path; assert not Path('/inputs/expected').exists(); "
        "Path('result.txt').write_text('HELLO TASK\\n')"
    )
    isolated = replace(
        recipe(),
        submission_command=ProcessCommand(
            ("python", "/submission/solution.py"), timeout_seconds=15
        ),
        prediction_paths=("result.txt",),
    )
    result = LocalRunService(
        DockerEnvironment(tmp_path / "runtime"),
        manager(),
        tmp_path / "runs",
        node_id="local",
        recipes=(isolated,),
    ).run(
        request,
        FixtureAgent(
            "from pathlib import Path; Path('solution.py').write_text(" + repr(program) + ")"
        ),
    )
    assert result.status == "completed"
    assert json.loads(result.feedback_json) == {"passed": True}
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    events = records.read_events(EventQuery(attempt_id=result.attempt_id, limit=500)).items
    assert any(
        event.event_type == "phase.started" and event.payload.get("phase") == "submission"
        for event in events
    )


def test_real_timeout_and_cancel(tmp_path):
    request = setup_task(tmp_path, evaluation=False)
    environment = DockerEnvironment(tmp_path / "runtime")
    service = LocalRunService(environment, manager(), tmp_path / "runs", node_id="local")
    result = service.run(
        replace(request, timeout_seconds=0.2), FixtureAgent("import time; time.sleep(10)")
    )
    assert result.status == "timed_out"
    assert result.cleanup_complete and result.lease_released
    cancel = Event()
    cancel.set()
    service = LocalRunService(environment, manager(), tmp_path / "runs", node_id="local")
    result = service.run(request, FixtureAgent("import time; time.sleep(10)"), cancellation=cancel)
    assert result.status == "cancelled"
    assert result.cleanup_complete and result.lease_released


def test_real_symlink_and_background_cleanup(tmp_path):
    request = setup_task(tmp_path, evaluation=False)
    environment = DockerEnvironment(tmp_path / "runtime")
    result = LocalRunService(environment, manager(), tmp_path / "runs", node_id="local").run(
        request,
        FixtureAgent(
            "import os, subprocess; "
            "subprocess.Popen(['python','-c','import time; time.sleep(10)']); "
            "os.symlink('/etc/passwd','result.txt')"
        ),
    )
    assert result.status == "failed"
    assert result.cleanup_complete and result.lease_released


def test_real_readonly_input_and_wrong_answer(tmp_path):
    request = setup_task(tmp_path)
    code = """from pathlib import Path
try:
    Path('data/input.txt').write_text('changed')
    raise AssertionError('readonly mount was writable')
except OSError:
    pass
Path('result.txt').write_text('wrong answer')
"""
    result = LocalRunService(
        DockerEnvironment(tmp_path / "runtime"),
        manager(),
        tmp_path / "runs",
        node_id="local",
        recipes=(recipe(),),
    ).run(request, FixtureAgent(code))
    assert result.status == "completed"
    assert json.loads(result.feedback_json) == {"passed": False}
    assert result.cleanup_complete and result.lease_released


def test_runtime_lifecycle_and_collection_guards(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = DockerEnvironment(tmp_path / "runtime", log_limit_bytes=32)
    spec = SandboxSpec("guard", "solver", "python:3.12-slim", workspace, 1, 256 * 1024**2)
    handle = runtime.prepare(spec)
    assert runtime.prepare(spec) == handle
    with pytest.raises(ValueError):
        runtime.prepare(replace(spec, cpu_cores=0.5))
    try:
        with pytest.raises(ValueError):
            runtime.collect(handle, ("result.txt",), tmp_path / "too-early")
        runtime.start(
            handle,
            ProcessCommand(
                ("python", "-c", "print('a'*1000); open('result.txt','w').write('ok')"),
                timeout_seconds=15,
            ),
        )
        deadline = time.monotonic() + 15
        while (observed := runtime.observe(handle)).status == "running":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert observed.exit_code == 0 and observed.logs_truncated
        assert len(observed.stdout) == 32
    finally:
        assert runtime.cleanup(handle).complete
    with pytest.raises(ValueError):
        runtime.collect(handle, ("../private",), tmp_path / "outside")
    with pytest.raises(ValueError):
        runtime.collect(handle, ("result.txt",), workspace / "nested")
    artifact = runtime.collect(handle, ("result.txt", "absent"), tmp_path / "frozen")
    assert artifact.missing == ("absent",)
    assert (artifact.root / "result.txt").read_text() == "ok"
    assert runtime.cleanup(handle).complete
    with pytest.raises(ValueError):
        runtime.prepare(replace(spec, key="private", phase="scorer", private_home=workspace))
    with pytest.raises(ValueError):
        runtime.prepare(
            replace(
                spec,
                key="mount",
                readonly_inputs=(InputMount(workspace, "/workspace,bind-propagation=shared"),),
            )
        )
