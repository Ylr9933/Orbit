"""Independent adapter tests use authored fixtures, never benchmark test answers."""

import importlib
import json
from pathlib import Path

import pytest

from agent_infra.benchmarks.api import CandidateRef, PlanRequest
from agent_infra.benchmarks.execution_api import NativeInvocation
from agent_infra.environments.api import ProcessCommand


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    for package in ("harbor-runtime", "tb-science"):
        monkeypatch.syspath_prepend(str(root / "adapters" / package / "src"))
    module = importlib.import_module("agent_infra_tb_science")
    monkeypatch.setattr(module, "runner_digest", lambda: "sha256:" + "1" * 64)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda argv, **kw: module.REVISION if "rev-parse" in argv else "",
    )
    (tmp_path / "task.toml").write_text("""
[task]
name = "synthetic"
[environment]
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
[agent]
timeout_sec = 120.0
[verifier]
timeout_sec = 30.0
environment_mode = "separate"
[verifier.environment]
network_mode = "no-network"
""")
    (tmp_path / "instruction.md").write_text("Synthetic task, not benchmark material")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test.sh").write_text("exit 0")
    instance = module.Adapter()
    catalog = instance.discover(tmp_path)
    request = PlanRequest(
        selection=("synthetic",),
        candidate=CandidateRef(
            candidate_id="oracle",
            agent="oracle",
            agent_version="1.0.0",
            model="none",
            configuration_digest="sha256:" + "0" * 64,
        ),
    )
    return instance, instance.plan(catalog, request), tmp_path


def test_native_mapping_preserves_clocks_resources_visibility(adapter):
    instance, plan, _ = adapter
    assert not instance.validate(plan)
    phase = plan.phases[0]
    assert phase.budget.clock == "native_agent" and phase.budget.wall_seconds == 120
    assert phase.resources.disk_bytes == 10240 * 1024**2
    assert "solver" not in next(m for m in phase.materials if m.material_id == "tests").readers
    invocation = instance.invocation(plan)
    assert invocation.cancellation_grace_seconds == 90
    instance.validate_execution(plan, invocation)
    with pytest.raises(ValueError, match="no longer matches"):
        instance.validate_execution(plan, invocation.model_copy(update={"outputs": ()}))


@pytest.mark.parametrize("mutation", ["gpu", "compose", "shared", "over_budget", "model"])
def test_unsupported_profiles_rejected_before_launch(adapter, mutation):
    instance, plan, path = adapter
    task = path / "task.toml"
    data = task.read_text()
    if mutation == "gpu":
        task.write_text(data.replace("gpus = 0", "gpus = 1"))
    elif mutation == "compose":
        (path / "tests" / "docker-compose.yaml").write_text("services: {}")
    elif mutation == "shared":
        task.write_text(data.replace('"separate"', '"shared"'))
    elif mutation == "over_budget":
        task.write_text(data.replace("cpus = 1", "cpus = 2"))
    else:
        plan = plan.model_copy(
            update={
                "request": plan.request.model_copy(
                    update={
                        "candidate": plan.request.candidate.model_copy(update={"agent": "codex"})
                    }
                )
            }
        )
    assert instance.validate(plan)[0].severity == "error"


def test_native_failure_is_never_scored_as_zero(adapter, tmp_path):
    instance, _, _ = adapter
    assert instance.interpret(tmp_path)["evaluation"] == "unknown"
    result = tmp_path / "outputs/trials/one/result.json"
    result.parent.mkdir(parents=True)
    body = {
        "id": "native-id",
        "verifier_environment_mode": "separate",
        "verifier_result": {"rewards": {"reward": 0.0}},
        "exception_info": None,
    }
    result.write_text(json.dumps(body))
    assert instance.interpret(tmp_path)["metrics"] == {"reward": 0.0}
    body["exception_info"] = {"exception_type": "VerifierError"}
    result.write_text(json.dumps(body))
    assert instance.interpret(tmp_path)["evaluation"] == "failed"
    assert instance.interpret(tmp_path)["metrics"] == {}


def test_default_grace_keeps_bm01_serialization_compatible():
    invocation = NativeInvocation(command=ProcessCommand(("true",), cwd="."))
    assert "cancellation_grace_seconds" not in invocation.model_dump()
    with pytest.raises(ValueError):
        invocation.model_copy(update={"cancellation_grace_seconds": 121}).model_validate_json(
            invocation.model_copy(update={"cancellation_grace_seconds": 121}).model_dump_json()
        )


def test_native_cleanup_requires_receipt_and_live_daemon_absence(adapter, monkeypatch, tmp_path):
    from agent_infra.environments.api import CleanupResult
    from agent_infra.environments.execution_api import ExecutionHandle, ExecutionSpec
    from agent_infra.environments.managed_process import ManagedProcessBackend

    module = importlib.import_module("agent_infra_harbor.backend")
    backend = module.HarborBackend(tmp_path / "native")
    handle = ExecutionHandle("op", backend.backend_id, None, "digest")
    monkeypatch.setattr(ManagedProcessBackend, "cleanup", lambda *args: CleanupResult(True))
    monkeypatch.setattr(
        backend,
        "spec",
        lambda _: ExecutionSpec(
            run_id="run",
            attempt_id="attempt",
            unit_id="unit",
            phase_id="phase",
            command=ProcessCommand(("true",), cwd="."),
            workspace=str(tmp_path),
        ),
    )
    assert not backend.cleanup(handle).complete
    (tmp_path / "native-cleanup.json").write_text(
        json.dumps({"complete": True, "projects": ["infra_" + "a" * 24 + "__env"]})
    )
    monkeypatch.setattr(module, "remaining", lambda _: ["container"])
    assert not backend.cleanup(handle).complete
    monkeypatch.setattr(module, "remaining", lambda _: [])
    assert backend.cleanup(handle).complete

    def unavailable(_):
        raise RuntimeError("daemon offline")

    monkeypatch.setattr(module, "remaining", unavailable)
    assert not backend.cleanup(handle).complete
