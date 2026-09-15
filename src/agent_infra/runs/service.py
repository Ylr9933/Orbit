"""Single-node orchestration through public module contracts."""

from __future__ import annotations

import json
import math
import shutil
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

from agent_infra.agents.api import (
    AgentPermissionMode,
    AgentPlacement,
    AgentRunRequest,
    CommandAgentAdapter,
)
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
from agent_infra.records.local import LocalRunJournal
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
    ) -> None:
        self.environment = environment
        self.resources = resources
        self.state_dir = state_dir.resolve()
        self.node_id = node_id
        self.recipes = {recipe.evaluator_ref: recipe for recipe in recipes}
        if len(self.recipes) != len(recipes):
            raise ValueError("duplicate evaluation recipe")

    def run(
        self, request: RunRequest, agent: CommandAgentAdapter, *, cancellation: Event | None = None
    ) -> RunResult:
        run_id = uuid.uuid4().hex
        root = self.state_dir / run_id
        root.mkdir(parents=True, mode=0o700)
        journal = LocalRunJournal(root / "records")
        handles: list[EnvironmentHandle] = []
        lease = None
        submission: Submission | None = None
        status, evaluation_status, feedback = "failed", "not_requested", "{}"
        error: str | None = None
        cleanup_complete, released = True, False

        def phase(spec: SandboxSpec, command: ProcessCommand, paths: tuple[str, ...]) -> Submission:
            journal.event("phase_started", phase=spec.phase)
            handle = self.environment.prepare(spec)
            handles.append(handle)
            journal.event("environment_prepared", phase=spec.phase, handle_id=handle.id)
            self.environment.start(handle, command)
            cursor = LogCursor()
            deadline = time.monotonic() + command.timeout_seconds
            while True:
                if cancellation is not None and cancellation.is_set():
                    self.environment.cancel(handle)
                    raise _PhaseFailure("cancelled")
                observed = self.environment.observe(handle, cursor)
                cursor = observed.cursor
                if observed.status not in {"running", "prepared"}:
                    journal.event(
                        "phase_finished",
                        phase=spec.phase,
                        status=observed.status,
                        exit_code=observed.exit_code,
                        logs_truncated=observed.logs_truncated,
                    )
                    if observed.status != "exited" or observed.exit_code != 0:
                        raise _PhaseFailure(
                            observed.status if observed.status != "exited" else "failed"
                        )
                    break
                if time.monotonic() > deadline:
                    self.environment.cancel(handle)
                    raise _PhaseFailure("timed_out")
                time.sleep(0.05)
            if not self.environment.cleanup(handle).complete:
                raise _PhaseFailure("cleanup_failed")
            return self.environment.collect(handle, paths, root / (spec.phase + "-submission"))

        try:
            if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
                raise ValueError("solver timeout must be positive and finite")
            task = load_task(request.task_manifest)
            snapshot = freeze_task(task)
            view = build_agent_view(task)
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
            journal.event("preparing", task_id=task.task_id, task_digest=snapshot.definition_digest)
            decision = self.resources.try_allocate(resource_request)
            lease = decision.lease
            if lease is None:
                status = decision.status.value
            else:
                journal.event("allocated", lease_id=lease.lease_id, node_id=lease.node_id)
                if lease.node_id != self.node_id:
                    raise ValueError("local runtime cannot execute a remote lease")
                workspace = root / "solver-workspace"
                materialize_agent_view(task, snapshot, workspace)
                prompt = "\n\n".join(
                    (workspace / path).read_text(encoding="utf-8")
                    for path in (*view.instructions, *view.user_context)
                    if (workspace / path).is_file()
                )
                prompt += "\nAvailable task materials:\n" + json.dumps(asdict(view), default=str)
                credential_home = None
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
                    ),
                    credential_home=credential_home,
                )
                if (launch.container_image or request.solver_image) != request.solver_image:
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
                    launch.container_image or request.solver_image,
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
                submission = phase(
                    solver_spec,
                    ProcessCommand(
                        launch.argv,
                        launch.cwd,
                        launch.stdin_text,
                        launch.environment,
                        request.timeout_seconds,
                    ),
                    paths,
                )
                if any(item["required"] and item["path"] in submission.missing for item in outputs):
                    raise ValueError("required submission output missing")
                if recipe is not None:
                    evaluation_status = "running"
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
                        )
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
                    scorer_result = phase(
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
                    result_file = scorer_result.root / recipe.result_path
                    if result_file.stat().st_size > 1024**2:
                        raise ValueError("scorer result too large")
                    payload = json.loads(result_file.read_text())
                    if not isinstance(payload, dict):
                        raise ValueError("scorer result must be an object")
                    if content_digest(scored.root) != scored.digest:
                        raise ValueError("submission changed during scoring")
                    if evaluation["feedback"] != "none":
                        feedback = json.dumps(recipe.project_feedback(payload), allow_nan=False)
                    evaluation_status = "completed"
                status = "completed"
        except _PhaseFailure as failure:
            status = str(failure)
            error = str(failure)
        except Exception as failure:
            # Exception details can contain private paths; retained only in controller journal.
            journal.event("controller_error", type=type(failure).__name__, detail=str(failure))
            status, error = "failed", "controller failure; consult private run records"
        finally:
            for handle in handles:
                try:
                    cleaned = self.environment.cleanup(handle).complete
                except Exception:
                    cleaned = False
                cleanup_complete = cleaned and cleanup_complete
            if lease is not None and cleanup_complete:
                try:
                    released = self.resources.release(lease.lease_id)
                except Exception:
                    released = False
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
            journal.finish(
                asdict(result)
                | {
                    "submission_root": str(result.submission_root)
                    if result.submission_root
                    else None
                }
            )
        return result
