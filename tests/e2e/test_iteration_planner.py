"""Real Docker two-round workflow and replaceable Planner; deterministic agents, no model calls."""

import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_infra.bootstrap.iteration import StudyActions
from agent_infra.environments import planner_client
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.recovery import inspect_local_image, recover_owned_containers
from agent_infra.projects.research import ResearchService
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources import (
    HostResourceSnapshot,
    LocalResourceManager,
    NodeCapacity,
    load_resource_request,
)
from agent_infra.runs.api import RunRequest
from agent_infra.runs.control_api import PreparedRun, SubmissionRequest
from agent_infra.runs.control_store import RunControlStore
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.planner import PlannerSessions
from agent_infra.runs.query import RunQueries
from agent_infra.runs.service import LocalRunService
from agent_infra.tasks import freeze_task, load_task
from tests.unit.projects.test_compilation import compile, setup
from tests.unit.runs.test_controller import CredentialFixture

pytestmark = pytest.mark.e2e

PLANNER_CODE = """
import json, subprocess, time
from pathlib import Path
assert not Path('/var/run/docker.sock').exists()
assert not Path('/workspace/private.txt').exists()
def call(action, **options):
    value = json.loads(subprocess.check_output(['python3','/inputs/planner-client.py', action,
                         '--json',json.dumps(options)],text=True))
    assert 'error' not in value, value
    return value['result']
state = call('context')['workflow']
assert len(state['actions']) == EXPECTED
key = next(iter(state['tasks']))
run = call('step', task_key=key, operation_id='round-' + str(EXPECTED))
assert call('step', task_key=key, operation_id='round-' + str(EXPECTED))['run_id'] == run['run_id']
while True:
    state = call('status')
    current = state['actions'][-1]['run']
    if current['state'] == 'finished':
        break
    time.sleep(.1)
assert current['result']['status'] == 'completed', current
result = call('read', run_id=run['run_id'])
artifact = next(a for a in result['artifacts'] if a['name'] == 'solver-submission')
files = call('read', run_id=run['run_id'],artifact_id=artifact['artifact_id'])
assert any(f['path']=='artifacts/report.json' for f in files['files'])
call('analysis', operation_id='analysis-'+str(EXPECTED), document={
    'results':[{'run_id':run['run_id'], 'artifact_id':artifact['artifact_id'],
                'member':'artifacts/report.json', 'data_version':'v1', 'code_version':'fixture-v1',
                'metrics':[{'name':'mean','pointer':'/mean','unit':'scalar','direction':'inspect'}]}],
    'observations':'mean measured', 'interpretation':'fixture only',
    'uncertainty':'no scientific inference', 'recommendation':'inspect results'})
print('fixture Planner complete')
"""


def setup_workflow(root, *, wall_seconds=300):
    compiler, project, workspace = setup(root)
    (workspace / "configs/resources/pilot.yaml").write_text(
        "version: 1\nrequest_id: pilot\nresources:\n  cpu: 0.5\n  memory: 512MiB\n"
    )
    compiled = compile(compiler, project)
    assert compiled["status"] == "compiled"
    manifest = Path(compiled["manifest"])
    task = load_task(manifest)
    image = inspect_local_image("python:3.12-slim")
    resources = LocalResourceManager(NodeCapacity("local", 1, 2 * 1024**3))
    resources.update_snapshot(
        HostResourceSnapshot("local", datetime.now(UTC), 2, 0, 0, 8 * 1024**3, 8 * 1024**3)
    )
    control_root = root / "state/controller"
    env = DockerEnvironment(control_root / "environments")
    records = LocalRecordsStore(control_root / "records")
    service = LocalRunService(
        env, resources, control_root / "work", node_id="local", records=records
    )
    agent = CredentialFixture(
        "from pathlib import Path; import json; "
        "Path('artifacts').mkdir(exist_ok=True); "
        "import csv, statistics; "
        "values=[float(r['value']) for r in csv.DictReader(Path('data/raw/input.csv').open())]; "
        "Path('artifacts/report.json').write_text(json.dumps({'mean':statistics.mean(values)}))"
    )
    request = RunRequest(
        manifest,
        manifest.parent / "control/resources.yaml",
        "python:3.12-slim",
        timeout_seconds=30,
        resolved_image=image,
        expected_snapshot=freeze_task(task),
    )
    prepared = PreparedRun(
        request, load_resource_request(request.resource_file), agent, compiled["compiled"]
    )
    control = LocalRunController(
        RunControlStore(control_root),
        service,
        records,
        resources,
        lambda _: prepared,
        lambda: resources.update_snapshot(
            HostResourceSnapshot("local", datetime.now(UTC), 2, 0, 0, 8 * 1024**3, 8 * 1024**3)
        ),
        lambda: recover_owned_containers(control_root / "environments"),
    )
    study = StudyActions(root / "state", control, RunQueries(control.store, records))
    context = ResearchService(compiler.store).context(project)
    workflow = study.iteration.authorize(
        project,
        "approve",
        {
            "authorization": "two deterministic CPU fixture runs",
            "expected_revision": 1,
            "expected_digest": context["digest"],
            "tasks": [
                asdict(
                    SubmissionRequest(task.task_id, task.revision, "fixture", timeout_seconds=30)
                )
            ],
            "max_experiments": 2,
            "total_seconds": 60,
            "wall_seconds": wall_seconds,
            "cpu": 0.5,
            "memory_bytes": 512 * 1024**2,
        },
    )
    return control, study, env, project, workflow


def wait(control, run_id, seconds=50):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = control.store.get(run_id)
        if run["state"] in {"finished", "quarantined"}:
            return run
        time.sleep(0.1)
    pytest.fail("Planner did not finish")


def test_replace_planner_between_two_real_experiments(tmp_path):
    control, study, env, project, workflow = setup_workflow(tmp_path)
    planners = None
    try:
        for index in range(2):
            planners = PlannerSessions(
                control,
                env,
                study.planner_call,
                Path(planner_client.__file__),
                inspect_local_image,
                adapter_factory=lambda image, index=index: CredentialFixture(
                    PLANNER_CODE.replace("EXPECTED", str(index))
                ),
            )
            run = planners.start(
                project,
                {
                    "workflow_id": workflow["workflow_id"],
                    "model": "fixture",
                    "image": "python:3.12-slim",
                    "cpu": 0.25,
                    "memory_bytes": 256 * 1024**2,
                    "timeout_seconds": 40,
                },
                f"planner-{index}",
            )
            outcome = wait(control, run["run_id"])
            assert outcome["result"]["status"] == "completed", (
                outcome,
                list((control.store.path.parent / "environments").glob("*/stderr.log")),
            )
            assert planners.close()
            assert not control.resources.active_leases
            assert not control.quarantined
        final = study.iteration.status(project, workflow["workflow_id"])
        assert final["state"] == "stopped" and final["stop_reason"] == "experiment_budget"
        assert len({a["run"]["run_id"] for a in final["actions"]}) == 2
        analyses = study.analysis.list(project, "analysis")["items"]
        assert len(analyses) == 2
        assert all(a["evidence"][0]["metrics"][0]["value"] == 2.0 for a in analyses)
        with pytest.raises(ValueError, match="only"):
            study.planner_call(project, workflow["workflow_id"], "authorize", {})
    finally:
        if planners:
            planners.close()
        control.close()


def test_controller_crash_recovers_planner_without_replaying_experiment(tmp_path):
    import multiprocessing
    import os
    import signal

    control, study, env, project, workflow = setup_workflow(tmp_path)

    def child():
        planner = PlannerSessions(
            control,
            env,
            study.planner_call,
            Path(planner_client.__file__),
            inspect_local_image,
            adapter_factory=lambda image: CredentialFixture(
                PLANNER_CODE.replace("EXPECTED", "0") + "\nimport time; time.sleep(300)"
            ),
        )
        planner.start(
            project,
            {
                "workflow_id": workflow["workflow_id"],
                "model": "fixture",
                "image": "python:3.12-slim",
                "cpu": 0.25,
                "memory_bytes": 256 * 1024**2,
                "timeout_seconds": 100,
            },
            "crash-planner",
        )
        time.sleep(100)

    process = multiprocessing.get_context("fork").Process(target=child)
    planner = None
    process.start()
    try:
        deadline = time.monotonic() + 50
        while len(study.analysis.list(project, "analysis")["items"]) != 1:
            assert process.is_alive()
            assert time.monotonic() < deadline
            time.sleep(0.1)
        first = study.iteration.status(project, workflow["workflow_id"])["actions"][0]["run"][
            "run_id"
        ]
        os.kill(process.pid, signal.SIGKILL)
        process.join(5)
        control.reconcile()
        assert not control.quarantined
        assert control.store.get(first)["result"]["status"] == "completed"
        planner = PlannerSessions(
            control,
            env,
            study.planner_call,
            Path(planner_client.__file__),
            inspect_local_image,
            adapter_factory=lambda image: CredentialFixture(PLANNER_CODE.replace("EXPECTED", "1")),
        )
        run = planner.start(
            project,
            {
                "workflow_id": workflow["workflow_id"],
                "model": "fixture",
                "image": "python:3.12-slim",
                "cpu": 0.25,
                "memory_bytes": 256 * 1024**2,
                "timeout_seconds": 40,
            },
            "recovered-planner",
        )
        assert wait(control, run["run_id"])["result"]["status"] == "completed"
        assert planner.close()
        final = study.iteration.status(project, workflow["workflow_id"])
        assert len(final["actions"]) == 2 and final["actions"][0]["run"]["run_id"] == first
        assert final["state"] == "stopped"
        assert not control.resources.active_leases
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
            control.reconcile()
        if planner:
            planner.close()
        control.close()
