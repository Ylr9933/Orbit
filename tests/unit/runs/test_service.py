"""Deterministic orchestration tests; FakeEnvironment does not provide isolation."""

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
import yaml

from agent_infra.agents.api import (
    AgentEvent,
    AgentEventKind,
    AgentLaunchPlan,
    AgentPlacement,
)
from agent_infra.contracts.files import content_digest
from agent_infra.environments.api import (
    CleanupResult,
    EnvironmentHandle,
    LogCursor,
    Observation,
    ProcessCommand,
    Submission,
)
from agent_infra.records import (
    AttemptTrajectoryBuilder,
    DataClass,
    EventQuery,
    RecordingPolicy,
    Visibility,
)
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources.api import HostResourceSnapshot, NodeCapacity
from agent_infra.resources.local import LocalResourceManager
from agent_infra.runs.api import RunRequest
from agent_infra.runs.service import LocalRunService
from agent_infra.tasks.execution import EvaluationRecipe

ROOT = Path(__file__).resolve().parents[3]


class FixtureAgent:
    """A deterministic command fixture, never a real model Agent."""

    def __init__(
        self, code="from pathlib import Path; Path('result.txt').write_text('HELLO TASK\\n')"
    ):
        self.code = code

    def create_launch_plan(self, request, *, credential_home=None):
        return AgentLaunchPlan(
            "fixture", AgentPlacement.CONTAINER, ("python", "-c", self.code), "/workspace", None
        )


class TraceFixtureAgent(FixtureAgent):
    def decode_events(self, lines):
        for sequence, line in enumerate(lines):
            yield AgentEvent(
                sequence,
                AgentEventKind.MESSAGE,
                "fixture.message",
                {"role": "assistant", "text": line},
            )


def setup_task(tmp_path, *, evaluation=True):
    task = tmp_path / "task"
    shutil.copytree(ROOT / "examples/task-packages/file-result", task)
    manifest = task / "task.yaml"
    if not evaluation:
        data = yaml.safe_load(manifest.read_text())
        data["evaluation"] = {"state": "none"}
        manifest.write_text(yaml.safe_dump(data))
    resource = tmp_path / "resources.yaml"
    resource.write_text("version: 1\nrequest_id: fixture\nresources:\n  cpu: 1\n  memory: 256MiB\n")
    return RunRequest(manifest, resource, "python:3.12-slim", timeout_seconds=15)


def manager():
    resource = LocalResourceManager(NodeCapacity("local", 1, 256 * 1024**2))
    resource.update_snapshot(
        HostResourceSnapshot("local", datetime.now(UTC), 1, 0, 0, 512 * 1024**2, 512 * 1024**2)
    )
    return resource


def recipe():
    return EvaluationRecipe(
        "example:text-exact-v1",
        "python:3.12-slim",
        ProcessCommand(
            (
                "python",
                "-c",
                "from pathlib import Path; import json; "
                "passed=(Path('/submission/result.txt').read_text()=="
                "Path('/inputs/expected').read_text()); "
                "Path('result.json').write_text(json.dumps({'passed':passed,'private':'hidden'}))",
            ),
            timeout_seconds=15,
        ),
        ("expected",),
        lambda result: {"passed": result["passed"]},
    )


class FakeEnvironment:
    def __init__(self, *, outcome="exited", cleanup=True, start_fails=False, stdout=""):
        self.specs = {}
        self.outcome, self.clean, self.start_fails = outcome, cleanup, start_fails
        self.stdout = stdout
        self.removed = set()

    def prepare(self, spec):
        handle = EnvironmentHandle(spec.phase)
        self.specs[handle.id] = spec
        return handle

    def start(self, handle, command):
        if self.start_fails:
            raise RuntimeError("start failed")
        spec = self.specs[handle.id]
        if spec.phase == "solver":
            assert not (spec.workspace / "private").exists()
            assert not (spec.workspace / "task.yaml").exists()
            (spec.workspace / "result.txt").write_text("HELLO TASK\n")
        else:
            assert "solver" in self.removed
            assert spec.private_home is None
            (spec.workspace / "result.json").write_text('{"passed":true,"private":"hidden"}')

    def observe(self, handle, cursor=None):
        return Observation(self.outcome, 0, self.stdout, "", LogCursor(len(self.stdout), 0))

    def cancel(self, handle):
        return CleanupResult(self.clean)

    def cleanup(self, handle):
        if self.clean:
            self.removed.add(handle.id)
        return CleanupResult(self.clean)

    def collect(self, handle, paths, destination):
        assert handle.id in self.removed
        destination.mkdir()
        for path in paths:
            shutil.copyfile(self.specs[handle.id].workspace / path, destination / path)
        return Submission(destination, content_digest(destination), paths, ())


@pytest.mark.parametrize("evaluation", [True, False])
def test_optional_evaluation(tmp_path, evaluation):
    request = setup_task(tmp_path, evaluation=evaluation)
    env = FakeEnvironment()
    result = LocalRunService(
        env, manager(), tmp_path / "runs", node_id="local", recipes=(recipe(),)
    ).run(request, FixtureAgent())
    assert result.status == "completed"
    assert result.cleanup_complete and result.lease_released
    assert result.evaluation_status == ("completed" if evaluation else "not_requested")
    assert set(env.specs) == ({"solver", "scorer"} if evaluation else {"solver"})
    assert result.feedback_json == ('{"passed": true}' if evaluation else "{}")
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    assert records.get_run(result.run_id).status == "completed"
    assert records.get_attempt(result.attempt_id).status == "completed"


def test_declared_evaluator_cannot_be_silently_skipped(tmp_path):
    env = FakeEnvironment()
    result = LocalRunService(env, manager(), tmp_path / "runs", node_id="local").run(
        setup_task(tmp_path), FixtureAgent()
    )
    assert result.status == "failed"
    assert result.evaluation_status == "not_run"
    assert not env.specs and result.lease_id is None


def test_run_records_trace_artifacts_evaluation_and_reward(tmp_path):
    env = FakeEnvironment(stdout="observable agent message")
    result = LocalRunService(
        env, manager(), tmp_path / "runs", node_id="local", recipes=(recipe(),)
    ).run(setup_task(tmp_path), TraceFixtureAgent())
    assert result.status == "completed"
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    events = records.read_events(EventQuery(attempt_id=result.attempt_id, limit=500)).items
    event_types = {event.event_type for event in events}
    assert {
        "task.snapshot",
        "policy.snapshot",
        "lease.granted",
        "process.started",
        "process.exited",
        "agent.message",
        "artifact.committed",
        "evaluation.finished",
        "reward.assigned",
        "lease.released",
    } <= event_types
    artifacts = records.list_artifacts(result.attempt_id)
    assert {artifact.name for artifact in artifacts} == {
        "agent-visible-task-snapshot",
        "solver-submission",
        "scorer-submission",
    }
    scorer = next(artifact for artifact in artifacts if artifact.name == "scorer-submission")
    assert scorer.visibility is Visibility.EVALUATOR
    assert scorer.data_class is DataClass.PRIVATE_EVALUATION
    scorer_producer = next(
        event.context.producer_id
        for event in events
        if event.event_type == "environment.ready" and event.payload.get("phase") == "scorer"
    )
    assert all(
        event.visibility is Visibility.EVALUATOR
        and event.data_class is DataClass.PRIVATE_EVALUATION
        for event in events
        if event.context.producer_id == scorer_producer
    )
    trajectory = AttemptTrajectoryBuilder(records).build(result.attempt_id)
    assert len(trajectory.steps) == 1
    assert "result_reward_rl_candidate" in trajectory.eligibility.eligible_for


def test_recording_limits_are_visible_in_trace_eligibility(tmp_path):
    service = LocalRunService(
        FakeEnvironment(stdout="long observable output"),
        manager(),
        tmp_path / "runs",
        node_id="local",
        recording_policy=RecordingPolicy(
            stream_bytes_per_job=5,
            total_bytes_per_attempt=5,
        ),
    )
    result = service.run(setup_task(tmp_path, evaluation=False), TraceFixtureAgent())
    assert result.status == "completed"
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    events = records.read_events(EventQuery(attempt_id=result.attempt_id, limit=500)).items
    assert any(event.event_type == "capture.truncated" for event in events)
    trajectory = AttemptTrajectoryBuilder(records).build(result.attempt_id)
    assert "capture_incomplete" in trajectory.eligibility.limitations


@pytest.mark.parametrize("outcome", ["failed", "timed_out", "oom"])
def test_execution_failure_still_cleans(tmp_path, outcome):
    env = FakeEnvironment(outcome=outcome)
    service = LocalRunService(env, manager(), tmp_path / "runs", node_id="local")
    result = service.run(setup_task(tmp_path, evaluation=False), FixtureAgent())
    assert result.status == outcome
    assert result.lease_released and result.cleanup_complete
    records = LocalRecordsStore(tmp_path / "runs" / "_records")
    event_types = {
        event.event_type
        for event in records.read_events(EventQuery(attempt_id=result.attempt_id, limit=500)).items
    }
    assert {
        "job.failed",
        "phase.failed",
        "stream.committed",
        "environment.cleanup_finished",
    } <= event_types


def test_cleanup_failure_retains_lease(tmp_path):
    env = FakeEnvironment(cleanup=False)
    result = LocalRunService(env, manager(), tmp_path / "runs", node_id="local").run(
        setup_task(tmp_path, evaluation=False), FixtureAgent()
    )
    assert result.status == "cleanup_failed"
    assert not result.lease_released and not result.cleanup_complete
    assert result.lease_id


def test_start_failure_and_cancellation(tmp_path):
    request = setup_task(tmp_path, evaluation=False)
    for env in [FakeEnvironment(start_fails=True), FakeEnvironment()]:
        cancel = Event()
        cancel.set()
        result = LocalRunService(env, manager(), tmp_path / "runs", node_id="local").run(
            request, FixtureAgent(), cancellation=cancel
        )
        assert result.status in {"failed", "cancelled"}
        assert result.cleanup_complete and result.lease_released


def test_feedback_none(tmp_path):
    request = setup_task(tmp_path)
    data = yaml.safe_load(request.task_manifest.read_text())
    data["evaluation"]["feedback"] = "none"
    request.task_manifest.write_text(yaml.safe_dump(data))
    result = LocalRunService(
        FakeEnvironment(), manager(), tmp_path / "runs", node_id="local", recipes=(recipe(),)
    ).run(request, FixtureAgent())
    assert result.evaluation_status == "completed"
    assert json.loads(result.feedback_json) == {}


def test_unsatisfiable_does_not_start(tmp_path):
    request = setup_task(tmp_path, evaluation=False)
    request.resource_file.write_text(
        "version: 1\nrequest_id: fixture\nresources:\n  cpu: 2\n  memory: 256MiB\n"
    )
    env = FakeEnvironment()
    result = LocalRunService(env, manager(), tmp_path / "runs", node_id="local").run(
        replace(request), FixtureAgent()
    )
    assert result.status == "unsatisfiable"
    assert not env.specs and result.lease_id is None


def test_waiting_does_not_start(tmp_path):
    env = FakeEnvironment()
    resources = LocalResourceManager(NodeCapacity("local", 1, 256 * 1024**2))
    result = LocalRunService(env, resources, tmp_path / "runs", node_id="local").run(
        setup_task(tmp_path, evaluation=False), FixtureAgent()
    )
    assert result.status == "waiting"
    assert not env.specs


@pytest.mark.parametrize(
    "field,section",
    [
        ("evaluation", {"state": "unknown"}),
        ("execution_policy", {"state": "specified", "native_ref": "bench:budget"}),
        ("environment", {"state": "specified", "image": "another-image"}),
    ],
)
def test_unresolved_or_unsupported_requirements_fail_before_allocation(tmp_path, field, section):
    request = setup_task(tmp_path, evaluation=False)
    data = yaml.safe_load(request.task_manifest.read_text())
    data[field] = section
    request.task_manifest.write_text(yaml.safe_dump(data))
    env = FakeEnvironment()
    result = LocalRunService(env, manager(), tmp_path / "runs", node_id="local").run(
        request, FixtureAgent()
    )
    assert result.status == "failed"
    assert result.lease_id is None and not env.specs
