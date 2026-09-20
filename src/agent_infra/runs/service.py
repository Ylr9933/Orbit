"""Single-node orchestration through public module contracts and durable Records."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any, cast

from agent_infra.agents.api import (
    AgentEvent,
    AgentPermissionMode,
    AgentPlacement,
    AgentRunRequest,
    CommandAgentAdapter,
)
from agent_infra.agents.recording import agent_event_draft
from agent_infra.contracts.files import content_digest, relative_path, resolve_material
from agent_infra.environments.api import (
    Environment,
    EnvironmentHandle,
    InputMount,
    LogCursor,
    ProcessCommand,
    SandboxSpec,
    Submission,
)
from agent_infra.records import (
    AttemptManifest,
    CaptureStatus,
    DataClass,
    EventDraft,
    ProducerKind,
    RecordContext,
    RecordingPolicy,
    RecordsWriter,
    RunManifest,
    StreamRef,
    Visibility,
)
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources.api import ResourceManager
from agent_infra.runs.api import RunRequest, RunResult
from agent_infra.tasks import (
    build_agent_view,
    freeze_task,
    load_task,
    materialize_agent_view,
    validate_resource_plan,
)
from agent_infra.tasks.api import FieldState
from agent_infra.tasks.execution import EvaluationRecipe


class _PhaseFailure(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _PhaseOutcome:
    submission: Submission
    stdout: str
    stdout_stream: StreamRef
    stderr_stream: StreamRef
    artifact_id: str


class LocalRunService:
    """Synchronous coordinator; callers own node snapshots and trusted recipe registration."""

    def __init__(
        self,
        environment: Environment,
        resources: ResourceManager,
        state_dir: Path,
        *,
        node_id: str,
        recipes: tuple[EvaluationRecipe, ...] = (),
        records: RecordsWriter | None = None,
        recording_policy: RecordingPolicy | None = None,
    ) -> None:
        self.environment = environment
        self.resources = resources
        self.state_dir = state_dir.resolve()
        self.node_id = node_id
        self.recipes = {recipe.evaluator_ref: recipe for recipe in recipes}
        self.records = records or LocalRecordsStore(self.state_dir / "_records")
        self.recording_policy = recording_policy or RecordingPolicy()
        if len(self.recipes) != len(recipes):
            raise ValueError("duplicate evaluation recipe")

    def run(
        self,
        request: RunRequest,
        agent: CommandAgentAdapter,
        *,
        cancellation: Event | None = None,
        run_id: str | None = None,
        attempt_id: str | None = None,
    ) -> RunResult:
        run_id = run_id or uuid.uuid4().hex
        attempt_id = attempt_id or "attempt_" + uuid.uuid4().hex
        for identifier in (run_id, attempt_id):
            if not identifier or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for c in identifier
            ):
                raise ValueError("invalid run/attempt identity")
        root = self.state_dir / run_id
        root.mkdir(parents=True, mode=0o700)
        now = datetime.now(UTC)
        self.records.begin_run(
            RunManifest(
                run_id,
                now,
                {
                    "task_manifest_name": request.task_manifest.name,
                    "resource_file_name": request.resource_file.name,
                    "solver_image": request.solver_image,
                    "timeout_seconds": request.timeout_seconds,
                    "network": request.network,
                    "resolved_image": request.resolved_image,
                    "model": request.model,
                    "lineage": json.loads(request.lineage_json),
                },
                self.recording_policy,
            )
        )
        provider_hint = type(agent).__module__ + "." + type(agent).__qualname__
        self.records.begin_attempt(
            AttemptManifest(
                attempt_id,
                run_id,
                now,
                policy_snapshot={"adapter": provider_hint},
                environment_snapshot={"requested_solver_image": request.solver_image},
                coverage={
                    "agent_native_stream": "conditional",
                    "platform_tool_calls": "complete",
                    "environment_jobs": "complete",
                    "stdout_stderr": "complete",
                    "artifacts": "complete",
                    "evaluation": "complete",
                },
            )
        )
        run_sink = self.records.scoped_sink(
            RecordContext(run_id, attempt_id, f"run:{run_id}", ProducerKind.RUN)
        )
        resource_sink = self.records.scoped_sink(
            RecordContext(run_id, attempt_id, f"resource:{run_id}", ProducerKind.RESOURCE)
        )
        run_sink.append_events(
            (
                EventDraft("run.created", {"run_id": run_id}),
                EventDraft("attempt.started", {"attempt_id": attempt_id}),
            )
        )
        handles: list[EnvironmentHandle] = []
        lease = None
        submission: Submission | None = None
        status, evaluation_status, feedback = "failed", "not_requested", "{}"
        error: str | None = None
        cleanup_complete, released = True, False
        credential_home: Path | None = None
        recorded_stream_bytes = 0

        def append_limited(
            sink: Any,
            stream_id: str,
            chunk: bytes,
            offset: int,
        ) -> tuple[int, bool, bytes]:
            nonlocal recorded_stream_bytes
            stream_remaining = max(0, self.recording_policy.stream_bytes_per_job - offset)
            attempt_remaining = max(
                0, self.recording_policy.total_bytes_per_attempt - recorded_stream_bytes
            )
            kept = chunk[: min(stream_remaining, attempt_remaining)]
            if kept:
                sink.append_stream(stream_id, kept, offset)
                recorded_stream_bytes += len(kept)
            return offset + len(kept), len(kept) < len(chunk), kept

        def phase(
            spec: SandboxSpec,
            command: ProcessCommand,
            paths: tuple[str, ...],
            *,
            decode_agent: CommandAgentAdapter | None = None,
        ) -> _PhaseOutcome:
            phase_id = "phase_" + uuid.uuid4().hex
            phase_span = "span_" + uuid.uuid4().hex
            run_phase_sink = self.records.scoped_sink(
                RecordContext(
                    run_id,
                    attempt_id,
                    f"run:{run_id}",
                    ProducerKind.RUN,
                    phase_id,
                )
            )
            run_phase_sink.append_events(
                (
                    EventDraft(
                        "phase.started",
                        {"phase": spec.phase},
                        trace_id=attempt_id,
                        span_id=phase_span,
                    ),
                )
            )
            handle = self.environment.prepare(spec)
            handles.append(handle)
            job_id = "job_" + uuid.uuid4().hex
            job_span = "span_" + uuid.uuid4().hex
            environment_sink = self.records.scoped_sink(
                RecordContext(
                    run_id,
                    attempt_id,
                    f"environment:{handle.id}",
                    ProducerKind.ENVIRONMENT,
                    phase_id,
                )
            )
            private_evaluation = spec.phase == "scorer"
            stream_visibility = (
                Visibility.EVALUATOR if private_evaluation else Visibility.CONTROLLER
            )
            stream_class = (
                DataClass.PRIVATE_EVALUATION if private_evaluation else DataClass.INTERNAL
            )
            stdout_id, stderr_id = f"{job_id}:stdout", f"{job_id}:stderr"
            for stream_id, name in ((stdout_id, "stdout"), (stderr_id, "stderr")):
                environment_sink.start_stream(
                    stream_id,
                    name,
                    media_type="text/plain; charset=utf-8",
                    visibility=stream_visibility,
                    data_class=stream_class,
                )
            environment_sink.append_events(
                (
                    EventDraft(
                        "environment.ready",
                        {
                            "phase": spec.phase,
                            "handle_id": handle.id,
                            "image": spec.image,
                            "cpu_cores": spec.cpu_cores,
                            "memory_bytes": spec.memory_bytes,
                            "gpu_count": len(spec.gpu_device_ids),
                            "network": spec.network,
                        },
                        trace_id=attempt_id,
                        span_id=job_span,
                        parent_span_id=phase_span,
                        visibility=stream_visibility,
                        data_class=stream_class,
                    ),
                    EventDraft(
                        "job.submitted",
                        {
                            "job_id": job_id,
                            "argv": list(command.argv),
                            "cwd": command.cwd,
                            "timeout_seconds": command.timeout_seconds,
                            "environment_names": [name for name, _ in command.environment],
                        },
                        trace_id=attempt_id,
                        span_id=job_span,
                        parent_span_id=phase_span,
                        correlation={"job_id": job_id},
                        visibility=stream_visibility,
                        data_class=stream_class,
                    ),
                )
            )
            stdout_offset = stderr_offset = 0
            stdout_parts: list[str] = []
            stream_truncated = False
            terminal_status: str | None = None
            exit_code: int | None = None
            phase_error: BaseException | None = None
            terminal_observed = False
            try:
                self.environment.start(handle, command)
                environment_sink.append_events(
                    (
                        EventDraft(
                            "process.started",
                            {"job_id": job_id},
                            trace_id=attempt_id,
                            span_id=job_span,
                            parent_span_id=phase_span,
                            correlation={"job_id": job_id},
                            visibility=stream_visibility,
                            data_class=stream_class,
                        ),
                    )
                )
                cursor = LogCursor()
                deadline = time.monotonic() + command.timeout_seconds
                while True:
                    stop_reason = (
                        "cancelled"
                        if cancellation is not None and cancellation.is_set()
                        else "timed_out"
                        if time.monotonic() > deadline
                        else None
                    )
                    if stop_reason:
                        terminal_status = stop_reason
                        if not self.environment.cancel(handle).complete:
                            raise _PhaseFailure(stop_reason)
                    observed = self.environment.observe(handle, cursor)
                    if stop_reason:
                        # Cancellation proved the process stopped. Drain the final buffered
                        # output before finalizing streams, including a failed Agent turn.
                        observed = replace(observed, status=stop_reason)
                    cursor = observed.cursor
                    stdout_offset, stdout_cut, stdout_kept = append_limited(
                        environment_sink,
                        stdout_id,
                        observed.stdout.encode(),
                        stdout_offset,
                    )
                    stdout_parts.append(stdout_kept.decode("utf-8", errors="replace"))
                    stderr_offset, stderr_cut, _ = append_limited(
                        environment_sink,
                        stderr_id,
                        observed.stderr.encode(),
                        stderr_offset,
                    )
                    stream_truncated = (
                        stream_truncated or stdout_cut or stderr_cut or observed.logs_truncated
                    )
                    if observed.status not in {"running", "prepared"}:
                        terminal_observed = True
                        terminal_status, exit_code = observed.status, observed.exit_code
                        environment_sink.append_events(
                            (
                                EventDraft(
                                    "process.exited",
                                    {
                                        "job_id": job_id,
                                        "status": observed.status,
                                        "exit_code": observed.exit_code,
                                        "logs_truncated": stream_truncated,
                                    },
                                    trace_id=attempt_id,
                                    span_id=job_span,
                                    parent_span_id=phase_span,
                                    correlation={"job_id": job_id},
                                    visibility=stream_visibility,
                                    data_class=stream_class,
                                ),
                            )
                        )
                        if observed.status != "exited" or observed.exit_code != 0:
                            raise _PhaseFailure(
                                observed.status if observed.status != "exited" else "failed"
                            )
                        break
                    time.sleep(0.05)
            except BaseException as failure:
                phase_error = failure
                environment_sink.append_events(
                    (
                        EventDraft(
                            "job.failed",
                            {
                                "job_id": job_id,
                                "status": terminal_status or "failed",
                                "error_type": type(failure).__name__,
                            },
                            trace_id=attempt_id,
                            span_id=job_span,
                            parent_span_id=phase_span,
                            correlation={"job_id": job_id},
                            visibility=stream_visibility,
                            data_class=stream_class,
                        ),
                    )
                )
                run_phase_sink.append_events(
                    (
                        EventDraft(
                            "phase.failed",
                            {"phase": spec.phase, "status": terminal_status or "failed"},
                            trace_id=attempt_id,
                            span_id=phase_span,
                        ),
                    )
                )
            finally:
                capture = CaptureStatus.TRUNCATED if stream_truncated else CaptureStatus.COMPLETE
                if not terminal_observed:
                    capture = CaptureStatus.PARTIAL
                stdout_stream = environment_sink.finalize_stream(stdout_id, capture)
                stderr_stream = environment_sink.finalize_stream(stderr_id, capture)
                stream_events = [
                    EventDraft(
                        "stream.committed",
                        {
                            "job_id": job_id,
                            "stdout": asdict(stdout_stream),
                            "stderr": asdict(stderr_stream),
                        },
                        trace_id=attempt_id,
                        span_id=job_span,
                        parent_span_id=phase_span,
                        correlation={"job_id": job_id},
                        raw_refs=tuple(
                            stream.blob.digest
                            for stream in (stdout_stream, stderr_stream)
                            if stream.blob is not None
                        ),
                        capture_status=capture,
                        visibility=stream_visibility,
                        data_class=stream_class,
                    )
                ]
                if capture is CaptureStatus.TRUNCATED:
                    stream_events.append(
                        EventDraft(
                            "capture.truncated",
                            {
                                "job_id": job_id,
                                "stream_bytes_per_job": (
                                    self.recording_policy.stream_bytes_per_job
                                ),
                                "total_bytes_per_attempt": (
                                    self.recording_policy.total_bytes_per_attempt
                                ),
                            },
                            trace_id=attempt_id,
                            span_id=job_span,
                            parent_span_id=phase_span,
                            correlation={"job_id": job_id},
                            capture_status=CaptureStatus.TRUNCATED,
                            visibility=stream_visibility,
                            data_class=stream_class,
                        )
                    )
                environment_sink.append_events(tuple(stream_events))
                if decode_agent is not None:
                    self._record_agent_events(
                        decode_agent,
                        "".join(stdout_parts),
                        run_id,
                        attempt_id,
                        phase_id,
                        stdout_stream,
                    )
            cleaned = self.environment.cleanup(handle)
            environment_sink.append_events(
                (
                    EventDraft(
                        "environment.cleanup_finished",
                        {"complete": cleaned.complete, "reason": cleaned.reason},
                        trace_id=attempt_id,
                        span_id=job_span,
                        parent_span_id=phase_span,
                        visibility=stream_visibility,
                        data_class=stream_class,
                    ),
                )
            )
            if phase_error is not None:
                raise phase_error
            if not cleaned.complete:
                raise _PhaseFailure("cleanup_failed")
            collected = self.environment.collect(handle, paths, root / (spec.phase + "-submission"))
            artifact = environment_sink.commit_artifact(
                collected.root,
                name=spec.phase + "-submission",
                media_type="application/vnd.agent-infra.submission",
                visibility=Visibility.EVALUATOR if private_evaluation else Visibility.USER,
                data_class=(
                    DataClass.PRIVATE_EVALUATION if private_evaluation else DataClass.USER_PRIVATE
                ),
            )
            environment_sink.append_events(
                (
                    EventDraft(
                        "artifact.committed",
                        {
                            "artifact_id": artifact.artifact_id,
                            "name": artifact.name,
                            "digest": artifact.digest,
                            "size_bytes": artifact.size_bytes,
                            "missing": list(collected.missing),
                        },
                        trace_id=attempt_id,
                        span_id=phase_span,
                        artifact_refs=(artifact.artifact_id,),
                        visibility=artifact.visibility,
                        data_class=artifact.data_class,
                    ),
                )
            )
            run_phase_sink.append_events(
                (
                    EventDraft(
                        "phase.finished",
                        {"phase": spec.phase, "status": terminal_status, "exit_code": exit_code},
                        trace_id=attempt_id,
                        span_id=phase_span,
                    ),
                )
            )
            return _PhaseOutcome(
                collected,
                "".join(stdout_parts),
                stdout_stream,
                stderr_stream,
                artifact.artifact_id,
            )

        try:
            if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
                raise ValueError("solver timeout must be positive and finite")
            task = load_task(request.task_manifest)
            snapshot = freeze_task(task)
            if request.expected_snapshot is not None and snapshot != request.expected_snapshot:
                raise ValueError("frozen Task contents changed after preflight; compile again")
            view = build_agent_view(task)
            run_sink.append_events(
                (
                    EventDraft(
                        "task.snapshot",
                        {
                            "task_id": task.task_id,
                            "revision": task.revision,
                            "mode": task.mode,
                            "definition_digest": snapshot.definition_digest,
                            "material_digests": dict(snapshot.material_digests),
                        },
                    ),
                )
            )
            if task.execution_policy.state in {FieldState.UNKNOWN, FieldState.SPECIFIED}:
                raise ValueError("native execution policy needs an explicit runtime adapter")
            task_environment = json.loads(task.environment.value_json)
            if task.environment.state is FieldState.UNKNOWN or task_environment.get("native_ref"):
                raise ValueError("native or unresolved environment needs an explicit adapter")
            if task_environment.get("image", request.solver_image) != request.solver_image:
                raise ValueError("run image does not match task environment")
            if any(tool.required for tool in view.tools):
                raise ValueError("required task tools need an installed binding")
            if task.evaluation.state is FieldState.UNKNOWN:
                raise ValueError("evaluation must be resolved before execution")
            recipe = None
            evaluation = json.loads(task.evaluation.value_json)
            if task.evaluation.state is FieldState.SPECIFIED:
                evaluation_status = "pending"
                recipe = self.recipes.get(evaluation["evaluator_ref"])
                if recipe is None:
                    raise ValueError("declared evaluator has no isolated recipe")
                relative_path(recipe.result_path)
                if recipe.submission_command and not recipe.prediction_paths:
                    raise ValueError("submission execution needs explicit prediction paths")
                materials = {item.id: item for item in task.materials}
                for identifier in recipe.material_ids:
                    relative_path(identifier)
                    if (
                        identifier not in materials
                        or "evaluator" not in materials[identifier].audiences
                    ):
                        raise ValueError("recipe material is not evaluator-visible")
            if task.outputs.state is FieldState.UNKNOWN:
                raise ValueError("output requirements are unresolved")
            outputs = json.loads(view.outputs.value_json).get("items", [])
            paths = tuple(item["path"] for item in outputs)
            resource_request = replace(
                validate_resource_plan(task, request.resource_file), request_id=run_id
            )
            decision = self.resources.try_allocate(resource_request)
            lease = decision.lease
            resource_sink.append_events(
                (
                    EventDraft(
                        "lease.granted" if lease is not None else "lease.declined",
                        {
                            "status": decision.status.value,
                            "request": {
                                "cpu_cores": resource_request.cpu_cores,
                                "memory_bytes": resource_request.memory_bytes,
                                "gpu_count": resource_request.gpu.count,
                            },
                            "lease_id": lease.lease_id if lease else None,
                            "node_id": lease.node_id if lease else None,
                            "shortages": [asdict(item) for item in decision.shortages],
                        },
                    ),
                )
            )
            if lease is None:
                status = decision.status.value
            else:
                if lease.node_id != self.node_id:
                    raise ValueError("local runtime cannot execute a remote lease")
                workspace = root / "solver-workspace"
                materialize_agent_view(task, snapshot, workspace)
                task_artifact = run_sink.commit_artifact(
                    workspace,
                    name="agent-visible-task-snapshot",
                    media_type="application/vnd.agent-infra.task-snapshot",
                )
                prompt = "\n\n".join(
                    (workspace / path).read_text(encoding="utf-8")
                    for path in (*view.instructions, *view.user_context)
                    if (workspace / path).is_file()
                )
                prompt += "\nAvailable task materials:\n" + json.dumps(asdict(view), default=str)
                if request.credential_home is not None:
                    content_digest(request.credential_home)
                    credential_home = root / "agent-home"
                    shutil.copytree(request.credential_home, credential_home)
                launch = agent.create_launch_plan(
                    AgentRunRequest(
                        run_id,
                        prompt,
                        workspace,
                        AgentPlacement.CONTAINER,
                        AgentPermissionMode.OUTER_SANDBOX,
                        model=request.model,
                        reasoning_effort=request.reasoning_effort,
                    ),
                    credential_home=credential_home,
                )
                run_sink.append_events(
                    (
                        EventDraft(
                            "policy.snapshot",
                            {
                                "provider": launch.provider,
                                "placement": launch.placement.value,
                                "adapter": provider_hint,
                                "prompt_sha256": "sha256:"
                                + hashlib.sha256(prompt.encode()).hexdigest(),
                                "argv": list(launch.argv),
                                "environment_names": [
                                    name
                                    for name, _ in (
                                        *launch.environment,
                                        *request.connection_environment,
                                    )
                                ],
                                "task_artifact_id": task_artifact.artifact_id,
                            },
                            artifact_refs=(task_artifact.artifact_id,),
                        ),
                    )
                )
                approved_image = request.resolved_image or request.solver_image
                if (launch.container_image or approved_image) != approved_image:
                    raise ValueError("Agent image does not match approved run image")
                if launch.placement is not AgentPlacement.CONTAINER:
                    raise ValueError("this runner requires a container Agent plan")
                home_target = "/home/agent"
                for mount in launch.mounts:
                    if (
                        mount.source.resolve() == workspace.resolve()
                        and mount.target == "/workspace"
                    ):
                        continue
                    if credential_home is not None and mount.source.resolve() == credential_home:
                        home_target = mount.target
                        continue
                    raise ValueError("Agent plan requests an unapproved mount")
                solver_spec = SandboxSpec(
                    run_id + ":solver",
                    "solver",
                    launch.container_image or approved_image,
                    workspace,
                    lease.cpu_cores,
                    lease.memory_bytes,
                    lease.gpu_device_ids,
                    tuple(
                        InputMount(workspace / item.path, "/workspace/" + item.path)
                        for item in view.materials
                        if item.access == "read_only"
                    ),
                    credential_home,
                    home_target,
                    request.network,
                )
                solver_outcome = phase(
                    solver_spec,
                    ProcessCommand(
                        launch.argv,
                        launch.cwd,
                        launch.stdin_text,
                        (*launch.environment, *request.connection_environment),
                        request.timeout_seconds,
                    ),
                    paths,
                    decode_agent=agent,
                )
                submission = solver_outcome.submission
                if any(item["required"] and item["path"] in submission.missing for item in outputs):
                    raise ValueError("required submission output missing")
                if recipe is not None:
                    evaluation_status = "running"
                    evaluation_sink = self.records.scoped_sink(
                        RecordContext(
                            run_id,
                            attempt_id,
                            f"evaluator:{attempt_id}",
                            ProducerKind.EVALUATOR,
                        )
                    )
                    evaluation_span = "span_" + uuid.uuid4().hex
                    evaluation_sink.append_events(
                        (
                            EventDraft(
                                "evaluation.started",
                                {
                                    "evaluator_ref": recipe.evaluator_ref,
                                    "submission_artifact_id": solver_outcome.artifact_id,
                                },
                                trace_id=attempt_id,
                                span_id=evaluation_span,
                                artifact_refs=(solver_outcome.artifact_id,),
                            ),
                        )
                    )
                    scored = submission
                    if recipe.submission_command:
                        execution_workspace = root / "submission-workspace"
                        execution_workspace.mkdir(mode=0o700)
                        scored = phase(
                            SandboxSpec(
                                run_id + ":submission",
                                "submission",
                                recipe.submission_image or recipe.image,
                                execution_workspace,
                                lease.cpu_cores,
                                lease.memory_bytes,
                                lease.gpu_device_ids,
                                (InputMount(submission.root, "/submission"),),
                            ),
                            recipe.submission_command,
                            recipe.prediction_paths,
                        ).submission
                        if scored.missing:
                            raise ValueError("prediction outputs missing")
                    if freeze_task(task) != snapshot:
                        raise ValueError("task changed before evaluation")
                    private_root = root / "evaluation-inputs"
                    private_root.mkdir(mode=0o700)
                    mounts = [InputMount(scored.root, "/submission")]
                    for identifier in recipe.material_ids:
                        material = next(item for item in task.materials if item.id == identifier)
                        source = resolve_material(task.root, material.source)
                        target = private_root / identifier
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if source.is_dir():
                            shutil.copytree(source, target)
                        else:
                            shutil.copyfile(source, target)
                        if content_digest(target) != dict(snapshot.material_digests)[identifier]:
                            raise ValueError("evaluation material changed during copy")
                        mounts.append(InputMount(target, "/inputs/" + identifier))
                    scorer_workspace = root / "scorer-workspace"
                    scorer_workspace.mkdir(mode=0o700)
                    if content_digest(scored.root) != scored.digest:
                        raise ValueError("submission changed before scoring")
                    scorer_outcome = phase(
                        SandboxSpec(
                            run_id + ":scorer",
                            "scorer",
                            recipe.image,
                            scorer_workspace,
                            lease.cpu_cores,
                            lease.memory_bytes,
                            lease.gpu_device_ids,
                            tuple(mounts),
                        ),
                        recipe.scorer,
                        (recipe.result_path,),
                    )
                    result_file = scorer_outcome.submission.root / recipe.result_path
                    if result_file.stat().st_size > 1024**2:
                        raise ValueError("scorer result too large")
                    payload = json.loads(result_file.read_text())
                    if not isinstance(payload, dict):
                        raise ValueError("scorer result must be an object")
                    if content_digest(scored.root) != scored.digest:
                        raise ValueError("submission changed during scoring")
                    public_feedback: dict[str, Any] = {}
                    if evaluation["feedback"] != "none":
                        public_feedback = recipe.project_feedback(payload)
                        feedback = json.dumps(public_feedback, allow_nan=False)
                    evaluation_events = [
                        EventDraft(
                            "evaluation.finished",
                            {
                                "evaluator_ref": recipe.evaluator_ref,
                                "result_artifact_id": scorer_outcome.artifact_id,
                                "feedback": public_feedback,
                            },
                            trace_id=attempt_id,
                            span_id=evaluation_span,
                            artifact_refs=(scorer_outcome.artifact_id,),
                        )
                    ]
                    reward = _feedback_reward(public_feedback)
                    if reward is not None:
                        evaluation_events.append(
                            EventDraft(
                                "reward.assigned",
                                {
                                    "name": "task_result",
                                    "value": reward,
                                    "target_id": attempt_id,
                                    "source": "evaluator",
                                    "evaluator_ref": recipe.evaluator_ref,
                                    "assignment_version": "evaluation-feedback-v1",
                                },
                                trace_id=attempt_id,
                                span_id=evaluation_span,
                            )
                        )
                    evaluation_sink.append_events(tuple(evaluation_events))
                    evaluation_status = "completed"
                status = "completed"
        except _PhaseFailure as failure:
            status = str(failure)
            error = str(failure)
        except Exception as failure:
            run_sink.append_events(
                (
                    EventDraft(
                        "controller.error",
                        {"type": type(failure).__name__, "detail": str(failure)},
                    ),
                )
            )
            status, error = "failed", "controller failure; consult private run records"
        finally:
            for handle in handles:
                try:
                    cleaned = self.environment.cleanup(handle).complete
                except Exception:
                    cleaned = False
                cleanup_complete = cleaned and cleanup_complete
            if credential_home is not None and credential_home.exists():
                try:
                    shutil.rmtree(credential_home)
                    credential_cleaned = True
                except OSError:
                    credential_cleaned = False
                cleanup_complete = credential_cleaned and cleanup_complete
                run_sink.append_events(
                    (
                        EventDraft(
                            "credential.cleanup_finished",
                            {"complete": credential_cleaned},
                            data_class=DataClass.CREDENTIAL,
                        ),
                    )
                )
            if lease is not None and cleanup_complete:
                try:
                    released = self.resources.release(lease.lease_id)
                except Exception:
                    released = False
                resource_sink.append_events(
                    (
                        EventDraft(
                            "lease.released",
                            {"lease_id": lease.lease_id, "released": released},
                        ),
                    )
                )
            if evaluation_status in {"pending", "running"} and status not in {
                "waiting",
                "unsatisfiable",
            }:
                evaluation_status = "failed" if evaluation_status == "running" else "not_run"
            if not cleanup_complete or (lease is not None and not released):
                if status == "completed":
                    status = "cleanup_failed"
            result = RunResult(
                run_id,
                attempt_id,
                status,
                evaluation_status,
                feedback,
                submission.root if submission else None,
                submission.digest if submission else None,
                cleanup_complete,
                released,
                lease.lease_id if lease else None,
                error,
            )
            result_payload = cast(dict[str, object], asdict(result))
            self.records.finish_attempt(attempt_id, status=status, result=result_payload)
            self.records.finish_run(run_id, status=status)
        return result

    def _record_agent_events(
        self,
        agent: CommandAgentAdapter,
        stdout: str,
        run_id: str,
        attempt_id: str,
        phase_id: str,
        native_stream: StreamRef,
    ) -> None:
        decoder = getattr(agent, "decode_events", None)
        if decoder is None:
            return
        sink = self.records.scoped_sink(
            RecordContext(
                run_id,
                attempt_id,
                f"agent:{attempt_id}",
                ProducerKind.AGENT,
                phase_id,
                f"session:{attempt_id}",
            )
        )
        raw_refs = (native_stream.blob.digest,) if native_stream.blob is not None else ()
        try:
            decoded = cast(Iterator[AgentEvent], decoder(iter(stdout.splitlines())))
            drafts = tuple(agent_event_draft(event, raw_refs) for event in decoded)
            sink.append_events(drafts)
        except Exception as failure:
            sink.append_events(
                (
                    EventDraft(
                        "capture.gap",
                        {"source": "agent_normalizer", "error_type": type(failure).__name__},
                        raw_refs=raw_refs,
                        capture_status=CaptureStatus.PARTIAL,
                    ),
                )
            )


def _feedback_reward(feedback: Mapping[str, object]) -> float | None:
    for key in ("reward", "score"):
        value = feedback.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
            return float(value)
    passed = feedback.get("passed")
    if isinstance(passed, bool):
        return 1.0 if passed else 0.0
    return None
