"""Resolve compiled Projects at the composition boundary; Runs only sees neutral values."""

import json
from pathlib import Path

from agent_infra.agents.api import AgentCapability
from agent_infra.agents.codex import CODEX_REASONING_EFFORTS, CodexAdapter
from agent_infra.environments.preparation_locks import resolve_environment_lock
from agent_infra.environments.preparation_store import EnvironmentCatalog
from agent_infra.environments.recovery import inspect_local_image
from agent_infra.projects.compilation_api import CompiledExperiment
from agent_infra.projects.compiler import CompilationService
from agent_infra.projects.local import LocalProjectStore
from agent_infra.runs.api import RunRequest
from agent_infra.runs.control_api import ControlError, PreparedRun, SubmissionRequest
from agent_infra.tasks import build_agent_view, freeze_task, load_task, validate_resource_plan
from agent_infra.tasks.api import FieldState


def prepare_compiled_run(state: Path, request: SubmissionRequest) -> PreparedRun:
    if request.provider != "codex":
        raise ControlError(
            "provider_unavailable",
            "this controller supports codex; other container credentials need an adapter",
        )
    if (
        request.reasoning_effort is not None
        and request.reasoning_effort not in CODEX_REASONING_EFFORTS
    ):
        raise ControlError("invalid_request", "unsupported Codex reasoning effort")
    if not request.network:
        raise ControlError(
            "network_required", "Codex requires model network access; submit with --network"
        )
    resolved = CompilationService(LocalProjectStore(state / "projects")).resolve(
        request.task_id, request.task_revision
    )
    compiled = CompiledExperiment.from_dict(resolved["compiled"])
    manifest = Path(resolved["manifest"])
    task = load_task(manifest)
    if freeze_task(task) != compiled.task.snapshot:
        raise ControlError("task_changed", "frozen task changed; recompile the experiment")
    view = build_agent_view(task)
    if any(tool.required for tool in view.tools):
        raise ControlError("tool_binding_required", "required task tools need installed bindings")
    if task.execution_policy.state in {FieldState.UNKNOWN, FieldState.SPECIFIED}:
        raise ControlError(
            "policy_adapter_required", "native execution policy requires a runtime adapter"
        )
    if task.evaluation.state is not FieldState.NONE:
        raise ControlError(
            "evaluator_required", "controller currently accepts research tasks without evaluation"
        )
    if task.outputs.state is FieldState.UNKNOWN:
        raise ControlError("outputs_required", "resolve output requirements before compilation")
    environment = json.loads(task.environment.value_json)
    image = environment.get("image")
    if not isinstance(image, str) or not image or environment.get("native_ref"):
        raise ControlError(
            "image_required",
            "compile with an explicit existing image containing Codex and task dependencies",
        )
    environment_lock = None
    if environment.get("lock_id"):
        environment_lock = resolve_environment_lock(
            EnvironmentCatalog(state / "controller/preparation"),
            compiled.project_id,
            environment["lock_id"],
            inspect_local_image,
            agent="codex",
        )
        if image != environment_lock["image_id"]:
            raise ControlError("environment_changed", "frozen image differs from validated lock")
    image_id = inspect_local_image(image, provider="codex")
    adapter = CodexAdapter(container_image=image_id)
    probe = adapter.probe()
    if not probe.available or not probe.authenticated or not probe.container_auth_reusable:
        raise ControlError(
            "agent_not_ready",
            "run agent-infra agent doctor codex; "
            "install/login with file-based auth.json before submitting",
        )
    if AgentCapability.CONTAINER_EXECUTION not in adapter.descriptor.capabilities:
        raise ControlError("capability_missing", "provider does not support container execution")
    resource_file = manifest.parent / "control/resources.yaml"
    resources = validate_resource_plan(task, resource_file)
    lineage = compiled.to_dict()
    if environment_lock:
        lineage["environment_lock"] = environment_lock
    return PreparedRun(
        RunRequest(
            manifest,
            resource_file,
            image,
            request.timeout_seconds,
            request.network,
            model=request.model,
            reasoning_effort=request.reasoning_effort,
            resolved_image=image_id,
            expected_snapshot=compiled.task.snapshot,
            lineage_json=json.dumps(lineage),
        ),
        resources,
        adapter,
        lineage,
    )
