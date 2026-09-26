"""TB-Science mapping; execution remains in the reusable Harbor runtime package."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlparse

from agent_infra_harbor.backend import HarborBackend
from agent_infra_harbor.bundle import validate_bundle
from agent_infra_harbor.proxy import proxy_address
from agent_infra_harbor.request import BACKEND, FEATURES, HARBOR_REVISION, Request, runner_digest

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

REVISION = "0efab0e6d7c6af5886e838990352ab85484cc234"


def source_path(plan: ExecutionPlan) -> Path:
    return Path(unquote(urlparse(plan.suite.source.uri).path))


def task_config(path: Path) -> dict:
    return tomllib.loads((path / "task.toml").read_text())


def runtime_request(plan: ExecutionPlan) -> Request:
    params = {item.key: item.value for item in plan.request.parameters}
    allowed = {
        "cpu",
        "memory_mb",
        "codex_version",
        "auth_mode",
        "api_key_file",
        "proxy_url",
        "effort",
        "codex_bundle",
        "codex_bundle_digest",
    }
    if set(params) - allowed:
        raise ValueError("unsupported parameter; native task budgets cannot be overridden")
    candidate = plan.request.candidate
    if candidate.agent != "codex" and candidate.model != "none":
        raise ValueError("oracle/nop require model=none")
    if candidate.agent != "codex" and set(params) & {
        "codex_version",
        "auth_mode",
        "api_key_file",
        "proxy_url",
        "effort",
        "codex_bundle",
        "codex_bundle_digest",
    }:
        raise ValueError("Codex parameters require agent=codex")
    version = (
        params.get("codex_version", candidate.agent_version) if candidate.agent == "codex" else None
    )
    if candidate.agent == "codex" and version != candidate.agent_version:
        raise ValueError("codex_version must match candidate.agent_version")
    return Request(
        task=str(source_path(plan)),
        task_digest=plan.suite.source.digest,
        agent=candidate.agent,
        model=candidate.model if candidate.agent == "codex" else None,
        codex_version=version,
        auth_mode=params.get("auth_mode", "host_codex"),
        api_key_file=params.get("api_key_file"),
        proxy_url=params.get("proxy_url"),
        effort=params.get("effort", "medium"),
        cpu=float(params.get("cpu", "1")),
        memory_mb=int(params.get("memory_mb", "2048")),
        codex_bundle=params.get("codex_bundle"),
        codex_bundle_digest=params.get("codex_bundle_digest"),
    )


def resource_peak(config: dict, request: PlanRequest) -> tuple[float, int]:
    params = {item.key: item.value for item in request.parameters}
    default_cpu, default_mem = float(params.get("cpu", "1")), int(params.get("memory_mb", "2048"))
    envs = (config["environment"], config["verifier"].get("environment", config["environment"]))
    # Conservative peak: each phase may need Harbor's policy sidecar. Phases are sequential.
    return (
        max(float(e.get("cpus") or default_cpu) for e in envs) + 0.1,
        (max(int(e.get("memory_mb") or default_mem) for e in envs) + 128) * 1024**2,
    )


class Adapter:
    descriptor = AdapterDescriptor(
        adapter_id="tb-science", description="Pinned native Harbor trial"
    )

    def discover(self, source: Path) -> Catalog:
        # A selected task is the immutable source, not the whole checkout's .git/runtime files.
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        if commit != REVISION:
            raise ValueError("unsupported TB-Science checkout revision")
        changes = subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain", "--", "."], text=True
        )
        if changes:
            raise ValueError("task must be an unchanged upstream task")
        config = task_config(source)
        return Catalog(
            suite=SuiteRef(
                benchmark="terminal-bench-science",
                profile="single-cpu-separate-v1",
                source=PinnedSource(
                    uri=source.as_uri(), revision=REVISION, digest=content_digest(source)
                ),
                runner=PinnedSource(
                    uri="https://github.com/harbor-framework/harbor",
                    revision=HARBOR_REVISION,
                    digest=runner_digest(),
                ),
            ),
            units=(
                WorkUnit(
                    unit_id=config["task"]["name"],
                    native_id=config["task"]["name"],
                    kind="native_job",
                ),
            ),
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        path = Path(unquote(urlparse(catalog.suite.source.uri).path))
        config = task_config(path)
        env = config["environment"]
        peak_cpu, peak_memory = resource_peak(config, request)
        materials = tuple(
            Material(
                material_id=name,
                source=PinnedSource(
                    uri=(path / name).as_uri(),
                    revision=REVISION,
                    digest=content_digest(path / name),
                ),
                purpose=purpose,
                readers=readers,
            )
            for name, purpose, readers in (
                ("instruction.md", "native instructions", ("solver", "admin")),
                ("environment", "native solver image context", ("admin",)),
                ("tests", "private native verifier image context", ("grader", "admin")),
                ("solution", "reference oracle, never a model-agent input", ("admin",)),
            )
            if (path / name).exists()
        )
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=catalog.units,
            phases=(
                Phase(
                    phase_id="trial",
                    kind="native",
                    owner="native",
                    backend=BACKEND,
                    required_capabilities=FEATURES,
                    resources=ResourceRequirements(
                        cpu_cores=peak_cpu,
                        memory_bytes=peak_memory,
                        disk_bytes=env["storage_mb"] * 1024**2 if env.get("storage_mb") else None,
                        gpu_count=env.get("gpus"),
                        allocator="local",
                    ),
                    budget=Budget(
                        wall_seconds=int(
                            config["agent"]["timeout_sec"]
                            + config["verifier"]["timeout_sec"]
                            + 2400
                        ),
                        clock="wall",
                    ),
                    materials=materials,
                    native_config=PinnedSource(
                        uri=(path / "task.toml").as_uri(),
                        revision=REVISION,
                        digest=content_digest(path / "task.toml"),
                    ),
                ),
            ),
            retry=RetryPolicy(owner="none", max_attempts=1),
            limitations=(
                "CPU-only single-step native profile; no leaderboard submission",
                "Native Docker storage_mb is recorded, not enforced",
                "Unspecified verifier CPU/memory receive explicit operator defaults",
                "Native Codex requires explicit version/model/auth; "
                "runtime evidence is separate from declarations",
            ),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        try:
            path = source_path(plan)
            config = task_config(path)
            if len(plan.units) != 1 or config.get("steps"):
                raise ValueError("only one single-step task is supported")
            verifier = config["verifier"]
            if verifier.get("environment_mode") != "separate":
                raise ValueError("separate verifier required")
            request = runtime_request(plan)
            cpu, memory = request.cpu, request.memory_mb
            if request.proxy_url:
                proxy_address(request.proxy_url)
                if request.agent != "codex" or any(
                    env.get("network_mode", "public") != "public"
                    for env in (config["environment"], config["agent"])
                ):
                    raise ValueError(
                        "proxy requires a native public solver network; cannot bypass policy"
                    )
            if request.codex_bundle:
                validate_bundle(request.codex_bundle, request.codex_bundle_digest)
            for env in (config["environment"], verifier.get("environment", config["environment"])):
                if (
                    env.get("gpus", 0)
                    or env.get("cpus", cpu) > cpu
                    or env.get("memory_mb", memory) > memory
                ):
                    raise ValueError("native task exceeds operator CPU/memory/zero-GPU envelope")
                if env.get("os", "linux") != "linux" or env.get("env") or env.get("mcp_servers"):
                    raise ValueError("unsupported OS/credential/MCP requirements")
            for folder in ("environment", "tests"):
                if any(
                    (path / folder / name).exists()
                    for name in (
                        "docker-compose.yaml",
                        "docker-compose.yml",
                        "compose.yaml",
                        "compose.yml",
                    )
                ):
                    raise ValueError("multi-service task requires a later capability profile")
            if runner_digest() != plan.suite.runner.digest:
                raise ValueError("installed Harbor implementation changed")
        except (ValueError, KeyError) as error:
            return (
                Issue(
                    code="unsupported_native_profile",
                    message=" ".join(str(error).split())[:200].rstrip(),
                ),
            )
        return ()

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation:
        issues = self.validate(plan)
        if issues:
            raise ValueError(issues[0].message)
        request = runtime_request(plan)
        config = task_config(source_path(plan))
        # An outer failure watchdog, distinct from Harbor's preserved phase clocks.
        timeout = config["agent"]["timeout_sec"] + config["verifier"]["timeout_sec"] + 2400
        return NativeInvocation(
            command=ProcessCommand(
                (sys.executable, "-m", "agent_infra_harbor.runner", request.model_dump_json()),
                cwd=".",
                timeout_seconds=timeout,
            ),
            outputs=(
                "trials",
                "native-job.json",
                "native-ownership.json",
                "native-cleanup.json",
                "attestations",
                "native-evidence.json",
                "evidence",
            ),
            cancellation_grace_seconds=90,
            max_artifact_bytes=256 * 1024**2,
        )

    def execution_backend(self, root: Path) -> HarborBackend:
        return HarborBackend(root)

    def validate_execution(self, plan: ExecutionPlan, invocation: NativeInvocation) -> None:
        if invocation != self.invocation(plan):
            raise ValueError("native invocation no longer matches the pinned task and runtime")

    def interpret(self, root: Path) -> dict:
        results = list((root / "outputs" / "trials").glob("*/result.json"))
        if len(results) != 1:
            return {
                "evaluation": "unknown",
                "protocol": "unknown",
                "metrics": {},
                "reason": "native result absent or ambiguous",
            }
        data = json.loads(results[0].read_bytes())
        rewards = (data.get("verifier_result") or {}).get("rewards")
        valid = data.get("verifier_environment_mode") == "separate"
        error = data.get("exception_info")
        scored = isinstance(rewards, dict) and bool(rewards) and not error and valid
        evidence_path = root / "outputs/native-evidence.json"
        evidence = (
            json.loads(evidence_path.read_bytes())
            if evidence_path.is_file()
            else {"capture_status": "unavailable"}
        )
        agent = (data.get("config") or {}).get("agent", {}).get("name", "unknown")
        return {
            "evaluation": "scored" if scored else "failed",
            "protocol": "valid" if valid else "unknown",
            "metrics": rewards if scored else {},
            "native_trial_id": data["id"],
            "native_exception": error,
            "failure_reason": {
                "ModelNotFoundError": "model_unavailable",
                "AgentAuthenticationError": "model_authentication_failed",
            }.get((error or {}).get("exception_type")),
            "source": str(results[0].relative_to(root)),
            "agent_native": "trials/*/agent (native format, when produced)",
            "submission": "not_requested",
            "profile": "native-codex" if agent == "codex" else "engineering-oracle-nop",
            "evidence": evidence,
        }
