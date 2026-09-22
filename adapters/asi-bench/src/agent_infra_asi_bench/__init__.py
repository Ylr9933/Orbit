"""Pinned ASI-Bench public produce/score adapter."""

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import ai4sci_bench

from agent_infra.benchmarks.api import (
    AdapterDescriptor,
    Budget,
    Catalog,
    ExecutionPlan,
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
from agent_infra.contracts.files import content_digest
from agent_infra.environments.api import ProcessCommand

from .backend import AsiBenchBackend
from .request import ASI_REVISION, BACKEND, FEATURES, Request


def _source_path(plan: ExecutionPlan) -> Path:
    return Path(unquote(urlparse(plan.suite.source.uri).path))


def _git_root(path: Path) -> Path:
    working = path if path.is_dir() else path.parent
    result = subprocess.run(
        ["git", "-C", str(working), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("ASI-Bench material must belong to a Git checkout")
    return Path(result.stdout.strip()).resolve()


def _require_pinned_clean(path: Path) -> Path:
    root = _git_root(path)
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != ASI_REVISION:
        raise ValueError("unsupported ASI-Bench checkout revision")
    relative = path.resolve().relative_to(root)
    changes = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--", str(relative)], text=True
    )
    if changes:
        raise ValueError(f"ASI-Bench material has local changes: {relative}")
    return root


def _runner_source() -> PinnedSource:
    if importlib.metadata.version("asibench") != "0.1.5":
        raise ValueError("ASI-Bench 0.1.5 from the pinned revision is required")
    package = Path(ai4sci_bench.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return PinnedSource(
        uri="https://github.com/XuehaiWang/asi.git",
        revision=ASI_REVISION,
        digest="sha256:" + digest.hexdigest(),
    )


def _parameters(request: PlanRequest) -> dict[str, str]:
    return {item.key: item.value for item in request.parameters}


class Adapter:
    descriptor = AdapterDescriptor(
        adapter_id="asi-bench", description="Pinned ASI-Bench public produce and score"
    )

    def discover(self, source: Path) -> Catalog:
        source = source.resolve()
        _require_pinned_clean(source)
        if not source.is_dir() or not source.name.endswith("__seed31415"):
            raise ValueError("source must be one public seed31415 instance directory")
        if not (source / "reference").is_dir():
            raise ValueError("public seed31415 reference directory is required")
        return Catalog(
            suite=SuiteRef(
                benchmark="ASI-Bench",
                profile="seed31415-single-fixture-v1",
                source=PinnedSource(
                    uri=source.as_uri(), revision=ASI_REVISION, digest=content_digest(source)
                ),
                runner=_runner_source(),
            ),
            units=(WorkUnit(unit_id=source.name, native_id=source.name, kind="single"),),
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        params = _parameters(request)
        tasks = Path(params.get("tasks_dir", "")).resolve()
        timeout = int(params.get("timeout_seconds", "300"))
        task_id = catalog.units[0].native_id.removesuffix("__seed31415")
        task_dir = tasks / Path(*task_id.split("."))
        scorer_policy = tasks.parent / "config" / "public_scorers.json"
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=tuple(unit for unit in catalog.units if unit.unit_id in request.selection),
            phases=(
                Phase(
                    phase_id="native-produce-and-public-score",
                    kind="evaluate",
                    owner="native",
                    backend=BACKEND,
                    required_capabilities=FEATURES,
                    resources=ResourceRequirements(gpu_count=0, allocator="local"),
                    budget=Budget(wall_seconds=timeout + 120, clock="outer_wall_clock"),
                    materials=(
                        Material(
                            material_id="public-instance",
                            source=catalog.suite.source,
                            purpose="native public seed31415 prompt, data, and reference",
                            readers=("solver", "grader", "admin"),
                        ),
                        Material(
                            material_id="public-task-scorer",
                            source=PinnedSource(
                                uri=task_dir.as_uri(),
                                revision=ASI_REVISION,
                                digest=content_digest(task_dir),
                            ),
                            purpose="native public task and scorer implementation",
                            readers=("grader", "admin"),
                        ),
                        Material(
                            material_id="public-scorer-policy",
                            source=PinnedSource(
                                uri=scorer_policy.as_uri(),
                                revision=ASI_REVISION,
                                digest=content_digest(scorer_policy),
                            ),
                            purpose="native public scorer revision policy",
                            readers=("grader", "admin"),
                        ),
                    ),
                ),
            ),
            retry=RetryPolicy(owner="none", max_attempts=1),
            limitations=(
                "Engineering fixture only; no model call, GPU, or leaderboard claim",
                "Public seed31415 local score is explicitly non-official",
                "Official seed42 scoring remains ASI-Bench authenticated external evaluation",
                "Host observes CPU/memory; this profile does not claim cgroup limits",
            ),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        try:
            params = _parameters(plan.request)
            if set(params) - {"prompt_level", "tasks_dir", "timeout_seconds"}:
                raise ValueError("unsupported parameter for ASI-Bench engineering profile")
            if len(plan.units) != 1 or plan.units[0].unit_id != plan.units[0].native_id:
                raise ValueError("exactly one unchanged native instance is required")
            if plan.request.candidate.agent != "fixture" or plan.request.candidate.model != "none":
                raise ValueError("BM02-B admits only the model-free fixture agent")
            source = _source_path(plan)
            _require_pinned_clean(source)
            if source.name != plan.units[0].native_id or not source.name.endswith("__seed31415"):
                raise ValueError("native seed31415 instance ID was changed")
            prompt = params.get("prompt_level", "b1")
            prompt_available = (source / f"prompt_{prompt}.md").is_file()
            if prompt not in {"b1", "b2", "b3", "b4"} or not prompt_available:
                raise ValueError("selected native prompt level is unavailable")
            tasks = Path(params.get("tasks_dir", ""))
            if not tasks.is_dir() or tasks.name != "tasks":
                raise ValueError("tasks_dir must identify the pinned ASI-Bench tasks directory")
            _require_pinned_clean(tasks)
            task_id = source.name.removesuffix("__seed31415")
            task_dir = tasks / Path(*task_id.split("."))
            if not task_dir.is_dir():
                raise ValueError("matching native task/scorer directory is unavailable")
            scorer_policy = tasks.parent / "config" / "public_scorers.json"
            if not scorer_policy.is_file():
                raise ValueError("public scorer policy is unavailable")
            _require_pinned_clean(scorer_policy)
            timeout = int(params.get("timeout_seconds", "300"))
            Request(
                instance_dir=str(source),
                instance_digest=plan.suite.source.digest,
                tasks_dir=str(tasks.resolve()),
                tasks_digest=content_digest(task_dir),
                scorer_policy_digest=content_digest(scorer_policy),
                task_id=task_id,
                instance_id=source.name,
                prompt_level=prompt,
                timeout_seconds=timeout,
            )
            if _runner_source().digest != plan.suite.runner.digest:
                raise ValueError("installed ASI-Bench implementation changed")
        except (OSError, ValueError, KeyError) as error:
            return (Issue(code="unsupported_native_profile", message=str(error)),)
        return ()

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation:
        issues = self.validate(plan)
        if issues:
            raise ValueError(issues[0].message)
        params = _parameters(plan.request)
        source = _source_path(plan)
        tasks = Path(params["tasks_dir"]).resolve()
        task_id = source.name.removesuffix("__seed31415")
        task_dir = tasks / Path(*task_id.split("."))
        scorer_policy = tasks.parent / "config" / "public_scorers.json"
        request = Request(
            instance_dir=str(source),
            instance_digest=plan.suite.source.digest,
            tasks_dir=str(tasks),
            tasks_digest=content_digest(task_dir),
            scorer_policy_digest=content_digest(scorer_policy),
            task_id=task_id,
            instance_id=source.name,
            prompt_level=params.get("prompt_level", "b1"),
            timeout_seconds=int(params.get("timeout_seconds", "300")),
        )
        base = f"{request.instance_id}__{request.prompt_level}"
        return NativeInvocation(
            command=ProcessCommand(
                (sys.executable, "-m", "agent_infra_asi_bench.runner", request.model_dump_json()),
                cwd=".",
                timeout_seconds=request.timeout_seconds + 120,
            ),
            outputs=(
                "native/run_metadata.json",
                f"native/{request.task_id}/{base}.json",
                f"native/{request.task_id}/{base}.outputs",
                f"native/instances/{request.instance_id}/framework_task_info.json",
                "benchflow_manifest.json",
                "benchflow_score.json",
                "native-result.json",
            ),
            cancellation_grace_seconds=15,
        )

    def execution_backend(self, root: Path) -> AsiBenchBackend:
        return AsiBenchBackend(root)

    def validate_execution(self, plan: ExecutionPlan, invocation: NativeInvocation) -> None:
        if invocation != self.invocation(plan):
            raise ValueError("native invocation no longer matches the pinned ASI-Bench plan")

    def interpret(self, root: Path) -> dict:
        path = root / "outputs" / "native-result.json"
        if not path.is_file():
            return {
                "evaluation": "unknown",
                "protocol": "unknown",
                "metrics": {},
                "reason": "native result absent",
            }
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = data.get("local_score_official") is False and data.get("official_score") is None
        scored = data.get("evaluation_status") == "completed" and valid
        return {
            "evaluation": "scored" if scored else "failed",
            "protocol": "valid" if valid else "invalid",
            "metrics": {"local_public_score": data.get("local_score")} if scored else {},
            "task_id": data.get("task_id"),
            "instance_id": data.get("instance_id"),
            "prompt_level": data.get("prompt_level"),
            "attempt_status": data.get("attempt_status"),
            "official_score": None,
            "submission": "not_requested",
            "profile": "seed31415-single-fixture-v1",
            "source": "outputs/benchflow_score.json",
        }
