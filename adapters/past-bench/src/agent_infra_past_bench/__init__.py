"""Pinned PAST-Bench family adapter with paired state-policy preservation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import past_bench
from past_bench.models.self_evolve import SelfEvolveSequenceDefinition
from past_bench.self_evolve_v2 import generate_manifest

from agent_infra.benchmarks.api import (
    AdapterDescriptor,
    Budget,
    Catalog,
    Condition,
    ExecutionPlan,
    FeedbackRule,
    Issue,
    Material,
    Phase,
    PinnedSource,
    PlanRequest,
    ResourceRequirements,
    RetryPolicy,
    StatePolicy,
    SuiteRef,
    WorkUnit,
)
from agent_infra.benchmarks.execution_api import NativeInvocation
from agent_infra.contracts.files import content_digest
from agent_infra.environments.api import ProcessCommand

from .backend import PastBenchBackend
from .request import (
    BACKEND,
    FEATURES,
    JUDGE_KEY_ENVS,
    NATIVE_AGENT_VERSION,
    PAST_REVISION,
    PAST_VERSION,
    SUPPORTED_AGENTS,
    Request,
)


def _parameters(request: PlanRequest) -> dict[str, str]:
    return {item.key: item.value for item in request.parameters}


def _source_path(plan: ExecutionPlan) -> Path:
    return Path(unquote(urlparse(plan.suite.source.uri).path))


def _git_root(path: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("PAST-Bench family must belong to a Git checkout")
    return Path(result.stdout.strip()).resolve()


def _family_identity(source: Path) -> tuple[Path, str]:
    root = _git_root(source)
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PAST_REVISION:
        raise ValueError("unsupported PAST-Bench checkout revision")
    relative = source.resolve().relative_to(root)
    if len(relative.parts) != 3 or relative.parts[0] != "self-evolve-tasks-v2":
        raise ValueError("source must be one PAST-Bench v2 family directory")
    required = (relative, Path("config.yaml"), Path("configs/agents.yaml"))
    changes = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--", *(str(item) for item in required)],
        text=True,
    )
    if changes:
        raise ValueError("PAST-Bench family/config/registry must be unchanged upstream files")
    if not (source / "family.yaml").is_file():
        raise ValueError("PAST-Bench family.yaml is required")
    return root, "/".join(relative.parts[1:])


def _sequence(root: Path, family_rel: str) -> SelfEvolveSequenceDefinition:
    with tempfile.TemporaryDirectory(prefix="agent-infra-past-plan-") as temporary:
        manifest = Path(temporary) / "manifest.yaml"
        generate_manifest(family_rel, out_path=manifest, repo_root=root)
        return SelfEvolveSequenceDefinition.from_yaml(manifest)


def _runner_source() -> PinnedSource:
    if importlib.metadata.version("past-bench") != PAST_VERSION:
        raise ValueError(f"PAST-Bench {PAST_VERSION} from the pinned revision is required")
    package = Path(past_bench.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return PinnedSource(
        uri="https://github.com/Gen-Verse/PAST-Bench.git",
        revision=PAST_REVISION,
        digest="sha256:" + digest.hexdigest(),
    )


def _native_policy(source: Path) -> PinnedSource:
    family = source / "family.yaml"
    return PinnedSource(uri=family.as_uri(), revision=PAST_REVISION, digest=content_digest(family))


def _unit(source: Path, family_rel: str, sequence: SelfEvolveSequenceDefinition) -> WorkUnit:
    policy = _native_policy(source)
    return WorkUnit(
        unit_id=family_rel.split("/")[-1],
        native_id=family_rel,
        kind="paired_sequence",
        episodes=tuple(episode.label for episode in sequence.episodes),
        conditions=(
            Condition(
                condition_id="with_persistence",
                state=StatePolicy(
                    session="fresh",
                    workspace="reset",
                    conversation="discard",
                    memory="native_scoped",
                    checkpoint="native_scoped",
                    scope="condition",
                    owner="past-bench",
                    native_policy=policy,
                ),
            ),
            Condition(
                condition_id="without_persistence",
                state=StatePolicy(
                    session="fresh",
                    workspace="reset",
                    conversation="discard",
                    memory="none",
                    checkpoint="none",
                    scope="condition",
                    owner="past-bench",
                    native_policy=policy,
                ),
            ),
        ),
    )


class Adapter:
    descriptor = AdapterDescriptor(
        adapter_id="past-bench",
        description="Pinned PAST-Bench ordered paired-family execution",
    )

    def discover(self, source: Path) -> Catalog:
        source = source.resolve()
        root, family_rel = _family_identity(source)
        sequence = _sequence(root, family_rel)
        return Catalog(
            suite=SuiteRef(
                benchmark="PAST-Bench",
                profile="paired-family-native-v1",
                source=PinnedSource(
                    uri=source.as_uri(),
                    revision=PAST_REVISION,
                    digest=content_digest(source),
                ),
                runner=_runner_source(),
            ),
            units=(_unit(source, family_rel, sequence),),
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        source = Path(unquote(urlparse(catalog.suite.source.uri).path))
        root, _ = _family_identity(source)
        params = _parameters(request)
        timeout = int(params.get("timeout_seconds", "21600"))
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=tuple(unit for unit in catalog.units if unit.unit_id in request.selection),
            phases=(
                Phase(
                    phase_id="native-paired-family",
                    kind="native",
                    owner="native",
                    backend=BACKEND,
                    required_capabilities=FEATURES,
                    resources=ResourceRequirements(
                        cpu_cores=1.0,
                        memory_bytes=2 * 1024**3,
                        gpu_count=0,
                        allocator="local",
                    ),
                    budget=Budget(wall_seconds=timeout, clock="outer_family_wall_clock"),
                    materials=(
                        Material(
                            material_id="native-family",
                            source=catalog.suite.source,
                            purpose="ordered tasks, graders, state and history policy",
                            readers=("admin",),
                        ),
                        Material(
                            material_id="native-config",
                            source=PinnedSource(
                                uri=(root / "config.yaml").as_uri(),
                                revision=PAST_REVISION,
                                digest=content_digest(root / "config.yaml"),
                            ),
                            purpose="native judge and runtime defaults",
                            readers=("admin",),
                        ),
                        Material(
                            material_id="native-agent-registry",
                            source=PinnedSource(
                                uri=(root / "configs" / "agents.yaml").as_uri(),
                                revision=PAST_REVISION,
                                digest=content_digest(root / "configs" / "agents.yaml"),
                            ),
                            purpose="native agent/profile/runtime mapping",
                            readers=("admin",),
                        ),
                    ),
                    native_config=_native_policy(source),
                ),
            ),
            retry=RetryPolicy(owner="none", max_attempts=1),
            feedback=(
                FeedbackRule(
                    recipient="admin",
                    fields=("sequence_summary", "paired_comparison", "mechanism_evidence"),
                    release="after_trial",
                    purpose="native paired-family reporting",
                ),
            ),
            limitations=(
                "The family and paired conditions are one atomic native job; "
                "episodes are not independently scheduled",
                "Engineering mode uses no model and produces non-official protocol evidence only",
                "Native mode supports pinned local runtimes; "
                "Docker sandbox equivalence is not claimed",
                "No platform summary or memory is injected into the tested agent",
                "Results are not a leaderboard submission and official is always false",
            ),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        try:
            params = _parameters(plan.request)
            allowed = {
                "agent_key_file",
                "agent_profile",
                "judge_key_env",
                "judge_key_file",
                "judge_model",
                "mode",
                "sandbox_tools",
                "timeout_seconds",
            }
            if set(params) - allowed:
                raise ValueError("unsupported PAST-Bench parameter")
            source = _source_path(plan)
            root, family_rel = _family_identity(source)
            sequence = _sequence(root, family_rel)
            expected = _unit(source, family_rel, sequence)
            if plan.units != (expected,):
                raise ValueError("family identity, episode order or paired state policy changed")
            mode = params.get("mode", "engineering")
            candidate = plan.request.candidate
            if mode == "engineering":
                if (candidate.agent, candidate.model) != ("protocol-fixture", "none"):
                    raise ValueError("engineering mode requires protocol-fixture with model none")
            elif mode == "native":
                if candidate.agent not in SUPPORTED_AGENTS or candidate.model == "none":
                    raise ValueError("native mode requires a supported PAST-Bench agent and model")
                if candidate.agent_version != NATIVE_AGENT_VERSION:
                    raise ValueError(f"native agent_version must identify {NATIVE_AGENT_VERSION}")
                key_file = params.get("agent_key_file", "")
                if not key_file or not Path(key_file).is_absolute():
                    raise ValueError(
                        "native mode requires an absolute private agent_key_file reference"
                    )
                judge_file = params.get("judge_key_file", "")
                judge_env = params.get("judge_key_env", "")
                if bool(judge_file) != bool(judge_env):
                    raise ValueError("judge_key_file and judge_key_env must be provided together")
                if judge_env and judge_env not in JUDGE_KEY_ENVS:
                    raise ValueError("unsupported judge_key_env")
            else:
                raise ValueError("mode must be engineering or native")
            if params.get("sandbox_tools", "false") not in {"true", "false"}:
                raise ValueError("sandbox_tools must be true or false")
            timeout = int(params.get("timeout_seconds", "21600"))
            if not 1 <= timeout <= 86400:
                raise ValueError("timeout_seconds is outside the supported range")
            if _runner_source() != plan.suite.runner:
                raise ValueError("installed PAST-Bench runner changed")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            return (Issue(code="unsupported_native_profile", message=str(error)),)
        return ()

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation:
        issues = self.validate(plan)
        if issues:
            raise ValueError(issues[0].message)
        params = _parameters(plan.request)
        source = _source_path(plan)
        root, family_rel = _family_identity(source)
        materials = {item.material_id: item for item in plan.phases[0].materials}
        request = Request(
            mode=params.get("mode", "engineering"),
            checkout_root=str(root),
            family_dir=str(source),
            family_rel=family_rel,
            family_digest=plan.suite.source.digest,
            config_digest=materials["native-config"].source.digest,
            registry_digest=materials["native-agent-registry"].source.digest,
            runner_digest=plan.suite.runner.digest,
            agent=plan.request.candidate.agent,
            agent_profile=params.get("agent_profile", ""),
            model=plan.request.candidate.model,
            agent_key_file=params.get("agent_key_file", ""),
            judge_key_file=params.get("judge_key_file", ""),
            judge_key_env=params.get("judge_key_env", ""),
            judge_model=params.get("judge_model", ""),
            sandbox_tools=params.get("sandbox_tools", "false") == "true",
            timeout_seconds=int(params.get("timeout_seconds", "21600")),
        )
        return NativeInvocation(
            command=ProcessCommand(
                (sys.executable, "-m", "agent_infra_past_bench.runner", request.model_dump_json()),
                cwd=".",
                timeout_seconds=request.timeout_seconds,
            ),
            outputs=("native-manifest.yaml", "past-output", "native-result.json"),
            cancellation_grace_seconds=20,
            max_log_bytes=32 * 1024**2,
            max_artifact_bytes=64 * 1024**2,
        )

    def execution_backend(self, root: Path) -> PastBenchBackend:
        return PastBenchBackend(root)

    def validate_execution(self, plan: ExecutionPlan, invocation: NativeInvocation) -> None:
        if invocation != self.invocation(plan):
            raise ValueError("native invocation no longer matches the pinned PAST-Bench plan")

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
        complete = data.get("pair_complete") is True and data.get("official") is False
        delta = data.get("evidence", {}).get("paired_delta", {})
        return {
            "evaluation": "scored" if complete else "failed",
            "protocol": "valid"
            if data.get("protocol") in {"valid", "engineering_valid"}
            else "review_required",
            "metrics": {"paired_evaluation_score_delta": delta.get("evaluation_avg_task_score")}
            if complete
            else {},
            "family": data.get("family"),
            "conditions": data.get("conditions"),
            "agent": data.get("agent"),
            "model": data.get("model"),
            "official": False,
            "submission": "not_requested",
            "profile": "paired-family-native-v1",
            "engineering_fixture": data.get("mode") == "engineering",
            "source": "outputs/native-result.json",
        }


__all__ = ["Adapter"]
