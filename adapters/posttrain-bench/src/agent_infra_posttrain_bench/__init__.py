"""Pinned PostTrainBench task planning and native HTCondor execution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import unquote, urlparse

from agent_infra.benchmarks.api import (
    AdapterDescriptor,
    Budget,
    Catalog,
    ExecutionPlan,
    FeedbackRule,
    Issue,
    Material,
    Phase,
    PinnedSource,
    PlanRequest,
    ResourceRequirements,
    RetryPolicy,
    SuiteRef,
    WorkUnit,
)
from agent_infra.benchmarks.execution_api import NativeInvocation
from agent_infra.environments.api import ProcessCommand

from .backend import PostTrainBackend
from .request import AGENT_VERSION, BACKEND, BASE_MODELS, FEATURES, REVISION, Request
from .source import (
    checkout_root,
    ensure_clean,
    private_file,
    runner_digest,
    scheduler_digest,
    task_digest,
    task_identity,
    validate_agent,
)

ENGINEERING_FEATURES = (
    "durable_operation",
    "bounded_logs",
    "native_evidence",
    "immutable_model_handoff",
    "large_artifact_reference",
)
PARAMETERS = {
    "max_model_bytes",
    "mode",
    "model_store",
    "model_to_train",
    "num_gpus",
    "num_hours",
    "request_cpus",
    "request_disk_gb",
    "request_memory_mb",
    "results_root",
    "scheduler_bin_dir",
    "timeout_seconds",
}


class _Values(TypedDict):
    mode: str
    model_to_train: str
    num_hours: int
    num_gpus: int
    request_cpus: int
    request_memory_mb: int
    request_disk_gb: int
    timeout_seconds: int
    results_root: str
    model_store: str
    scheduler_bin_dir: str
    max_model_bytes: int


def _parameters(request: PlanRequest) -> dict[str, str]:
    return {item.key: item.value for item in request.parameters}


def _source(plan: ExecutionPlan) -> Path:
    return Path(unquote(urlparse(plan.suite.source.uri).path))


def _int(params: dict[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(params.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside the supported range")
    return value


def _runner(root: Path) -> PinnedSource:
    return PinnedSource(
        uri="https://github.com/aisa-group/PostTrainBench.git",
        revision=REVISION,
        digest=runner_digest(root),
    )


def _task_source(source: Path) -> PinnedSource:
    return PinnedSource(uri=source.as_uri(), revision=REVISION, digest=task_digest(source))


def _native_policy(root: Path) -> PinnedSource:
    path = root / "src" / "run_task.sh"
    return PinnedSource(uri=path.as_uri(), revision=REVISION, digest=task_digest(path))


def _request_values(request: PlanRequest) -> _Values:
    params = _parameters(request)
    mode = params.get("mode", "engineering")
    num_hours = _int(params, "num_hours", 1 if mode == "engineering" else 10, 1, 50)
    num_gpus = _int(params, "num_gpus", 0 if mode == "engineering" else 1, 0, 8)
    timeout_default = 120 if mode == "engineering" else min(604800, (num_hours + 12) * 3600)
    return {
        "mode": mode,
        "model_to_train": params.get("model_to_train", ""),
        "num_hours": num_hours,
        "num_gpus": num_gpus,
        "request_cpus": _int(params, "request_cpus", 1 if mode == "engineering" else 16, 1, 128),
        "request_memory_mb": _int(
            params, "request_memory_mb", 2048 if mode == "engineering" else 131072, 1, 524288
        ),
        "request_disk_gb": _int(
            params, "request_disk_gb", 1 if mode == "engineering" else 400, 1, 2048
        ),
        "timeout_seconds": _int(params, "timeout_seconds", timeout_default, 1, 604800),
        "results_root": params.get("results_root", ""),
        "model_store": params.get("model_store", ""),
        "scheduler_bin_dir": params.get("scheduler_bin_dir", ""),
        "max_model_bytes": _int(
            params,
            "max_model_bytes",
            1024**3 if mode == "engineering" else 2 * 1024**4,
            1,
            2 * 1024**4,
        ),
    }


class Adapter:
    descriptor = AdapterDescriptor(
        adapter_id="posttrain-bench",
        description="Pinned PostTrainBench training, judges and immutable model handoff",
    )

    def discover(self, source: Path) -> Catalog:
        source = source.resolve()
        root, task = task_identity(source)
        return Catalog(
            suite=SuiteRef(
                benchmark="PostTrainBench",
                profile="training-trial-native-v1",
                source=_task_source(source),
                runner=_runner(root),
            ),
            units=(WorkUnit(unit_id=task, native_id=task, kind="native_job"),),
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        source = Path(unquote(urlparse(catalog.suite.source.uri).path))
        root = checkout_root(source)
        values = _request_values(request)
        mode = values["mode"]
        native = mode == "native"
        phase = Phase(
            phase_id="native-training-trial",
            kind="native",
            owner="native",
            backend=BACKEND,
            required_capabilities=FEATURES if native else ENGINEERING_FEATURES,
            resources=ResourceRequirements(
                cpu_cores=float(values["request_cpus"]),
                memory_bytes=values["request_memory_mb"] * 1024**2,
                gpu_count=values["num_gpus"],
                gpu_model="NVIDIA H100 80GB HBM3" if native else None,
                disk_bytes=values["request_disk_gb"] * 1024**3,
                allocator="external" if native else "local",
            ),
            budget=Budget(
                wall_seconds=values["timeout_seconds"],
                clock="scheduler_job_wall_clock" if native else "engineering_process_start",
            ),
            materials=(
                Material(
                    material_id="native-evaluation-task",
                    source=catalog.suite.source,
                    purpose="solver-visible evaluation tool, task metadata and native grading",
                    readers=("solver", "training", "public_eval", "grader", "admin"),
                ),
                Material(
                    material_id="native-runner-and-judges",
                    source=catalog.suite.runner,
                    purpose="training harness, evaluation, judge and aggregation protocol",
                    readers=("admin", "grader"),
                ),
            ),
            native_config=_native_policy(root),
        )
        units = tuple(
            unit for name in request.selection for unit in catalog.units if unit.unit_id == name
        )
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=units,
            phases=(phase,),
            retry=RetryPolicy(owner="none", max_attempts=1, native_rule=_native_policy(root)),
            feedback=(
                FeedbackRule(
                    recipient="solver",
                    fields=("public_evaluate_output", "timer"),
                    release="during_trial",
                    purpose="native trial experimentation within one fixed budget",
                ),
                FeedbackRule(
                    recipient="admin",
                    fields=("metrics", "judge_verdicts", "model_handoff"),
                    release="after_trial",
                    purpose="audit native score eligibility and frozen model",
                ),
            ),
            limitations=(
                "Training, public evaluation, judges and final evaluation remain one native job",
                "Evaluation retries are internal to that job and do not authorize another trial",
                "Native execution requires HTCondor GPU visibility isolation; "
                "local launch is refused",
                "The model snapshot is externally referenced; Records stores its content manifest",
                "Engineering mode invokes no Agent, model, GPU, judge service or Apptainer runtime",
                "No result is an official submission; protocol deviations remain explicit",
            ),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        try:
            params = _parameters(plan.request)
            if set(params) - PARAMETERS:
                raise ValueError("unsupported PostTrainBench parameter")
            source = _source(plan)
            root, task = task_identity(source)
            if plan.units != (WorkUnit(unit_id=task, native_id=task, kind="native_job"),):
                raise ValueError("native task identity changed")
            if plan.suite.runner != _runner(root) or plan.suite.source != _task_source(source):
                raise ValueError("PostTrainBench source changed")
            values = _request_values(plan.request)
            mode = values["mode"]
            candidate = plan.request.candidate
            if values["model_to_train"] not in BASE_MODELS:
                raise ValueError("model_to_train is not in the pinned PostTrainBench model set")
            if mode == "engineering":
                if (candidate.agent, candidate.model) != ("protocol-fixture", "none"):
                    raise ValueError("engineering mode requires protocol-fixture with model none")
                if values["num_gpus"] != 0:
                    raise ValueError("engineering mode must not request a GPU")
            elif mode == "native":
                if candidate.agent_version != AGENT_VERSION or candidate.model == "none":
                    raise ValueError(f"native candidate must identify {AGENT_VERSION}")
                if candidate.target_model is None:
                    raise ValueError("native mode requires a pinned target_model declaration")
                if candidate.target_model.uri != "hf://" + str(values["model_to_train"]):
                    raise ValueError("target_model does not match model_to_train")
                validate_agent(root, candidate.agent)
                if values["num_gpus"] < 1:
                    raise ValueError("native mode requires at least one GPU")
                for name in ("results_root", "model_store", "scheduler_bin_dir"):
                    path = Path(str(values[name]))
                    if not path.is_absolute():
                        raise ValueError(f"native mode requires absolute {name}")
                store = Path(str(values["model_store"]))
                if not store.is_dir() or store.is_symlink() or store.stat().st_mode & 0o077:
                    raise ValueError("model_store must be an existing private directory")
                results = Path(str(values["results_root"]))
                if not results.is_dir() or results.is_symlink():
                    raise ValueError("results_root must be an existing regular directory")
                config = root / ".env"
                private_file(config)
                scheduler_digest(Path(str(values["scheduler_bin_dir"])))
                ensure_clean(
                    root,
                    (
                        Path("agents") / candidate.agent / "solve.sh",
                        Path("agents") / candidate.agent / "api_keys.json",
                    ),
                )
            else:
                raise ValueError("mode must be engineering or native")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            return (Issue(code="unsupported_native_profile", message=str(error)),)
        return ()

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation:
        issues = self.validate(plan)
        if issues:
            raise ValueError(issues[0].message)
        values = _request_values(plan.request)
        source = _source(plan)
        root, task = task_identity(source)
        request = Request(
            checkout_root=str(root),
            task=task,
            task_digest=plan.suite.source.digest,
            runner_digest=plan.suite.runner.digest,
            agent=plan.request.candidate.agent,
            agent_config=plan.request.candidate.model,
            scheduler_digest=(
                scheduler_digest(Path(values["scheduler_bin_dir"]))
                if values["mode"] == "native"
                else ""
            ),
            **values,
        )
        return NativeInvocation(
            command=ProcessCommand(
                (
                    sys.executable,
                    "-m",
                    "agent_infra_posttrain_bench.runner",
                    request.model_dump_json(),
                ),
                cwd=".",
                timeout_seconds=request.timeout_seconds,
            ),
            outputs=("native-result.json", "model-handoff.json", "evidence"),
            cancellation_grace_seconds=30,
            max_log_bytes=64 * 1024**2,
            max_artifact_bytes=64 * 1024**2,
        )

    def execution_backend(self, root: Path) -> PostTrainBackend:
        return PostTrainBackend(root)

    def validate_execution(self, plan: ExecutionPlan, invocation: NativeInvocation) -> None:
        if invocation != self.invocation(plan):
            raise ValueError("native invocation no longer matches the pinned PostTrainBench plan")

    def interpret(self, root: Path) -> dict[str, Any]:
        path = root / "outputs" / "native-result.json"
        if not path.is_file():
            return {
                "evaluation": "unknown",
                "protocol": "unknown",
                "metrics": {},
                "reason": "native result absent",
            }
        data = json.loads(path.read_text(encoding="utf-8"))
        accuracy = data.get("raw_accuracy")
        protocol = data.get("protocol", "review_required")
        return {
            "evaluation": data.get("evaluation", "unknown"),
            "protocol": "valid" if protocol in {"engineering_valid", "native_valid"} else protocol,
            "metrics": {"raw_accuracy": accuracy} if accuracy is not None else {},
            "score_eligible": data.get("score_eligible", False),
            "model_handoff": data.get("model_handoff"),
            "judges": data.get("judges"),
            "agent": data.get("agent"),
            "agent_config": data.get("agent_config"),
            "target_model": data.get("model_to_train"),
            "official": False,
            "submission": "not_requested",
            "engineering_fixture": data.get("mode") == "engineering",
            "source": "outputs/native-result.json",
        }


__all__ = ["Adapter"]
