"""Meaningful protocol preservation and frozen-plan failure cases, without services."""

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_infra.benchmarks.api import (
    AdapterIdentity,
    BenchmarkOutcome,
    CapabilityProfile,
    Catalog,
    ExecutionPlan,
    Issue,
    PlanRequest,
    ResourceRequirements,
    WorkUnit,
)
from agent_infra.benchmarks.planning import (
    check_plan,
    freeze_plan,
    read_plan,
    write_plan,
)
from agent_infra.benchmarks.registry import AdapterError, LoadedAdapter
from agent_infra.benchmarks.testing import assert_planning_conformance

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/benchmark-adapter"


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> LoadedAdapter:
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    module = importlib.import_module("agent_infra_benchmark_example")
    return LoadedAdapter(
        module.Adapter(),
        AdapterIdentity(
            distribution="agent-infra-benchmark-example",
            version="0.1.0",
            entry_point="contract-demo",
            adapter_id="contract-demo",
            sdk_version="1.0",
        ),
    )


def request_for(name: str) -> PlanRequest:
    return PlanRequest.model_validate_json(
        (EXAMPLE / "fixtures" / name / "request.json").read_bytes()
    )


@pytest.mark.parametrize("name", ["asi-like", "terminal-like", "training-like", "sequence-like"])
def test_external_fixtures_roundtrip_and_preserve_native_semantics(
    loaded: LoadedAdapter, name: str, tmp_path: Path
) -> None:
    source = EXAMPLE / "fixtures" / name
    request = request_for(name)
    plan = assert_planning_conformance(loaded.implementation, source, request)
    frozen = freeze_plan(loaded, source, request)
    destination = tmp_path / "plan.json"
    write_plan(frozen, destination)
    assert read_plan(destination) == frozen
    assert destination.stat().st_mode & 0o777 == 0o600
    assert plan.suite.synthetic
    profile = CapabilityProfile.model_validate_json((EXAMPLE / "capabilities.json").read_bytes())
    assert check_plan(frozen, loaded, profile) == ()
    with pytest.raises(FileExistsError):
        write_plan(frozen, destination)
    assert read_plan(destination) == frozen

    if name == "asi-like":
        assert [phase.kind for phase in plan.phases] == ["solve", "submit"]
        assert all(rule.recipient != "optimizer" for rule in plan.feedback)
    elif name == "terminal-like":
        assert plan.phases[1].materials[0].readers == ("grader",)
        assert plan.phases[1].depends_on == ("solve",)
    elif name == "training-like":
        assert "solver" in plan.phases[0].materials[1].readers
        assert plan.phases[0].budget.wall_seconds == 36000
        assert plan.phases[0].resources.cpu_cores is None
        assert plan.request.candidate.target_model != plan.request.candidate.judge
        assert plan.feedback[0].release == "during_trial"
    else:
        unit = plan.units[0]
        assert unit.episodes == ("episode-1", "episode-2", "episode-3")
        on, off = unit.conditions
        assert on.state.session == off.state.session == "fresh"
        assert on.state.memory == "native_scoped" and off.state.memory == "none"
        assert plan.retry.max_attempts == 1


def test_missing_capabilities_are_not_inferred_from_installed_agent(loaded: LoadedAdapter) -> None:
    frozen = freeze_plan(loaded, EXAMPLE / "fixtures/sequence-like", request_for("sequence-like"))
    codes = {issue.code for issue in check_plan(frozen, loaded, CapabilityProfile())}
    assert codes == {"agent_unavailable", "backend_unavailable", "combination_unverified"}
    profile = json.loads((EXAMPLE / "capabilities.json").read_bytes())
    profile["backends"][-1]["features"] = []
    # A different Agent build is not covered by the profile's exact tuple.
    for claim in profile["combinations"]:
        claim["agent_version"] = "other-build"
    modified = CapabilityProfile.model_validate_json(json.dumps(profile))
    codes = {issue.code for issue in check_plan(frozen, loaded, modified)}
    assert "capability_missing" in codes and "combination_unverified" in codes


def test_digest_detects_plan_editing(loaded: LoadedAdapter, tmp_path: Path) -> None:
    frozen = freeze_plan(loaded, EXAMPLE / "fixtures/terminal-like", request_for("terminal-like"))
    payload = frozen.model_dump(mode="json")
    payload["plan"]["request"]["candidate"]["model"] = "changed-model"
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(AdapterError, match="digest mismatch"):
        read_plan(path)


def test_source_change_is_rejected(loaded: LoadedAdapter, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    protocol = source / "protocol.json"
    protocol.write_bytes((EXAMPLE / "fixtures/asi-like/protocol.json").read_bytes())
    frozen = freeze_plan(loaded, source, request_for("asi-like"))
    protocol.write_text(protocol.read_text() + "\n")
    codes = {issue.code for issue in check_plan(frozen, loaded, CapabilityProfile())}
    assert "source_changed" in codes and "plan_changed" in codes


def test_source_symlink_is_rejected(loaded: LoadedAdapter, tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(EXAMPLE / "fixtures/asi-like", target_is_directory=True)
    with pytest.raises(AdapterError, match="symlinks"):
        freeze_plan(loaded, alias, request_for("asi-like"))


@pytest.mark.parametrize("change", ["suite", "candidate", "episodes", "conditions"])
def test_adapter_cannot_rewrite_catalog_or_user_request(
    loaded: LoadedAdapter, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = loaded.implementation.plan

    def malicious(catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        payload = original(catalog, request).model_dump(mode="json")
        if change == "suite":
            payload["suite"]["profile"] = "other-profile"
        elif change == "candidate":
            payload["request"]["candidate"]["model"] = "other-model"
        elif change == "episodes":
            payload["units"][0]["episodes"].reverse()
        else:
            payload["units"][0]["conditions"][1]["state"]["memory"] = "native_scoped"
        return ExecutionPlan.model_validate_json(json.dumps(payload))

    monkeypatch.setattr(loaded.implementation, "plan", malicious)
    with pytest.raises(AdapterError, match="changed"):
        freeze_plan(loaded, EXAMPLE / "fixtures/sequence-like", request_for("sequence-like"))


def test_adapter_validation_is_mandatory(loaded: LoadedAdapter, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        loaded.implementation,
        "validate",
        lambda plan: (Issue(code="invalid_native_policy", message="Fixture native violation"),),
    )
    with pytest.raises(AdapterError, match="invalid_native_policy"):
        freeze_plan(loaded, EXAMPLE / "fixtures/asi-like", request_for("asi-like"))


@pytest.mark.parametrize("value", [True, "2", -1, float("nan"), float("inf")])
def test_resource_numbers_are_strict_and_finite(value: object) -> None:
    with pytest.raises(ValidationError):
        ResourceRequirements(cpu_cores=value)


def test_unknown_fields_versions_missing_conditions_and_cycles_fail(loaded: LoadedAdapter) -> None:
    plan = freeze_plan(
        loaded, EXAMPLE / "fixtures/terminal-like", request_for("terminal-like")
    ).plan
    payload = plan.model_dump(mode="json")
    for key, value in (("schema_version", True), ("schema_version", 2), ("unexpected", "ignored?")):
        with pytest.raises(ValidationError):
            ExecutionPlan.model_validate_json(json.dumps({**payload, key: value}))
    payload["phases"][0]["depends_on"] = ["verify"]
    with pytest.raises(ValidationError, match="topologically"):
        ExecutionPlan.model_validate_json(json.dumps(payload))
    with pytest.raises(ValidationError, match="conditions"):
        WorkUnit(unit_id="family", native_id="family", kind="paired_sequence", episodes=("e1",))


def test_outcome_does_not_conflate_score_success_validity_or_cleanup() -> None:
    result = BenchmarkOutcome(
        run_id="existing-run",
        attempt_id="existing-attempt",
        unit_id="family",
        execution="failed",
        evaluation="scored",
        protocol="review_required",
        cleanup="pending",
        capture="partial",
        submission="not_requested",
    )
    assert result.metrics == ()  # No invented zero score for infrastructure failure.
    assert result.execution != result.evaluation and result.cleanup == "pending"
