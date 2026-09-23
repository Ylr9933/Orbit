import json
import os
from pathlib import Path

import pytest
from agent_infra_past_bench import Adapter
from agent_infra_past_bench.engineering import run as run_engineering

from agent_infra.benchmarks.api import CandidateRef, Parameter, PlanRequest

PAST_ROOT = Path(os.environ.get("PAST_BENCH_CHECKOUT", "/missing/PAST-Bench"))
FAMILY = PAST_ROOT / "self-evolve-tasks-v2/memory_ability/SM01_preference_adoption"
pytestmark = pytest.mark.skipif(
    not FAMILY.is_dir(), reason="set PAST_BENCH_CHECKOUT to the pinned upstream checkout"
)


def request(*, mode: str = "engineering", agent: str = "protocol-fixture") -> PlanRequest:
    native = mode == "native"
    return PlanRequest(
        selection=(FAMILY.name,),
        candidate=CandidateRef(
            candidate_id="engineering" if not native else "native",
            agent=agent,
            agent_version="past-f8223517ae74" if native else "1.0.0",
            model="none" if not native else "MiniMax-M2.7",
            configuration_digest="sha256:" + "0" * 64,
        ),
        parameters=(
            Parameter(key="mode", value=mode),
            Parameter(key="timeout_seconds", value="120"),
            *((Parameter(key="agent_key_file", value="/private/key"),) if native else ()),
        ),
    )


def test_plan_preserves_family_order_pair_and_state_policy():
    adapter = Adapter()
    catalog = adapter.discover(FAMILY)
    plan = adapter.plan(catalog, request())
    assert adapter.validate(plan) == ()
    unit = plan.units[0]
    assert unit.kind == "paired_sequence" and len(unit.episodes) == 8
    assert [condition.condition_id for condition in unit.conditions] == [
        "with_persistence",
        "without_persistence",
    ]
    assert unit.conditions[0].state.memory == "native_scoped"
    assert unit.conditions[1].state.memory == "none"
    assert plan.retry.max_attempts == 1 and plan.retry.owner == "none"


def test_native_mode_rejects_non_native_agent_and_missing_key():
    adapter = Adapter()
    catalog = adapter.discover(FAMILY)
    fixture_native = adapter.plan(catalog, request(mode="native"))
    assert adapter.validate(fixture_native)[0].code == "unsupported_native_profile"

    no_key = request(mode="native", agent="hermes").model_copy(
        update={"parameters": (Parameter(key="mode", value="native"),)}
    )
    plan = adapter.plan(catalog, no_key)
    assert "agent_key_file" in adapter.validate(plan)[0].message


def test_engineering_profile_exercises_native_order_branches_and_aggregation(tmp_path: Path):
    from past_bench.self_evolve_v2 import generate_manifest

    manifest = tmp_path / "manifest.yaml"
    generate_manifest(
        "memory_ability/SM01_preference_adoption",
        out_path=manifest,
        repo_root=PAST_ROOT,
    )
    output = tmp_path / "output"
    run_engineering(manifest, output)
    comparison = json.loads((output / "sequence_comparison.json").read_text())
    evidence = json.loads((output / "state_evidence.json").read_text())["items"]
    assert comparison["delta"]["evaluation_avg_task_score"] > 0
    assert len(evidence) == 16
    assert len({item["session_id"] for item in evidence}) == 16
    assert any(item["history_mode"] == "from_anchor" for item in evidence)
    assert not any(
        item["state_visible"] for item in evidence if item["variant"] == "without_persistence"
    )


def test_interpret_labels_fixture_as_non_official(tmp_path: Path):
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "native-result.json").write_text(
        json.dumps(
            {
                "pair_complete": True,
                "official": False,
                "protocol": "engineering_valid",
                "mode": "engineering",
                "family": "memory_ability/SM01_preference_adoption",
                "conditions": ["with_persistence", "without_persistence"],
                "agent": "protocol-fixture",
                "model": "none",
                "evidence": {"paired_delta": {"evaluation_avg_task_score": 0.5}},
            }
        )
    )
    result = Adapter().interpret(tmp_path)
    assert result["protocol"] == "valid" and result["engineering_fixture"] is True
    assert result["official"] is False and result["submission"] == "not_requested"
