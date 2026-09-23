"""Two-candidate outer loop using synthetic score evidence, never a model or grader."""

import argparse
import importlib
import json
from pathlib import Path

import pytest

from agent_infra.benchmarks.api import AdapterIdentity, FeedbackRule, PlanRequest
from agent_infra.benchmarks.campaign_api import CampaignPolicy
from agent_infra.benchmarks.execution import PreparedExecution, prepare_execution, write_execution
from agent_infra.benchmarks.planning import FrozenPlan, canonical_digest, freeze_plan
from agent_infra.benchmarks.registry import LoadedAdapter
from agent_infra.bootstrap.benchmarks import benchmark_action
from agent_infra.projects.benchmark_campaign import BenchmarkCampaignService, BenchmarkCampaignStore

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/benchmark-execution"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    adapter = importlib.import_module("agent_infra_benchmark_process_example").Adapter()
    loaded = LoadedAdapter(
        adapter,
        AdapterIdentity(
            distribution="agent-infra-benchmark-process-example",
            version="0.1.0",
            entry_point="process-demo",
            adapter_id="process-demo",
            sdk_version="1.0",
        ),
    )
    request = PlanRequest.model_validate_json((EXAMPLE / "request.json").read_bytes())
    execution = prepare_execution(freeze_plan(loaded, EXAMPLE / "fixture", request), loaded)

    def with_feedback(
        value: PreparedExecution, *, candidate_id: str, config: str
    ) -> PreparedExecution:
        request = value.frozen_plan.plan.request
        candidate = request.candidate.model_copy(
            update={"candidate_id": candidate_id, "configuration_digest": "sha256:" + config * 64}
        )
        plan = value.frozen_plan.plan.model_copy(
            update={
                "request": request.model_copy(update={"candidate": candidate}),
                "feedback": (
                    FeedbackRule(
                        recipient="optimizer",
                        fields=("public_score",),
                        release="after_trial",
                        purpose="synthetic development comparison",
                    ),
                ),
            }
        )
        frozen_body = value.frozen_plan.model_dump(mode="json", exclude={"digest"})
        frozen_body["plan"] = plan.model_dump(mode="json")
        frozen = FrozenPlan.model_validate_json(
            json.dumps({**frozen_body, "digest": canonical_digest(frozen_body)})
        )
        body = value.model_dump(mode="json", exclude={"digest"})
        body["frozen_plan"] = frozen.model_dump(mode="json")
        return PreparedExecution.model_validate_json(
            json.dumps({**body, "digest": canonical_digest(body)})
        )

    baseline = with_feedback(execution, candidate_id="baseline", config="a")
    successor = with_feedback(execution, candidate_id="revised", config="b")
    policy = CampaignPolicy(
        campaign_id="two-candidates",
        max_trials=2,
        max_wall_seconds=120,
        allowed_candidate_fields=("configuration_digest",),
        feedback_metrics=("public_score",),
        selection_metric="public_score",
        direction="maximize",
    )
    service = BenchmarkCampaignService(BenchmarkCampaignStore(tmp_path / "state"))
    return service, baseline, successor, policy, tmp_path


def test_two_candidates_use_only_released_feedback_and_retain_lineage(setup):
    service, baseline, successor, policy, root = setup
    calls = []

    def submit(execution, operation, group, limit):
        calls.append((operation, group, limit))
        assert limit == 120 and group.startswith("bm06-")
        score = (
            0.4 if execution.frozen_plan.plan.request.candidate.candidate_id == "baseline" else 0.7
        )
        return {
            "run_id": "run-" + str(len(calls)),
            "attempt_id": "attempt-" + str(len(calls)),
            "state": "finished",
            "result": {
                "execution": "completed",
                "evaluation": "scored",
                "protocol": "valid",
                "capture": "complete",
                "cleanup_complete": True,
                "native_result": {
                    "metrics": {"public_score": score, "private_answer": 99},
                    "private_grader_log": "must never reach optimizer",
                },
            },
        }

    service.create(policy, baseline)
    first = service.submit(policy.campaign_id, "baseline", submit)
    assert first["candidates"][0]["feedback"] == {"public_score": 0.4}
    assert "private_answer" not in json.dumps(first)
    assert "outcome" not in first["candidates"][0]
    proposed = service.propose(policy.campaign_id, "baseline", successor)
    assert proposed["candidates"][1]["based_on_run_id"] == "run-1"
    assert proposed["candidates"][1]["changes"] == ["candidate.configuration_digest"]
    second = service.submit(policy.campaign_id, "revised", submit)
    assert second["selected_candidate_id"] == "revised"
    assert second["state"] == "stopped" and second["stop_reason"] == "trial_limit"
    assert len(second["candidates"]) == 2
    assert len(calls) == 2 and calls[0][1] == calls[1][1]
    restarted = BenchmarkCampaignService(BenchmarkCampaignStore(root / "state"))
    assert (
        restarted.refresh(policy.campaign_id, lambda _: pytest.fail("finished run re-polled"))
        == second
    )


def test_scope_and_feedback_are_checked_before_candidate_creation(setup):
    service, baseline, successor, policy, _ = setup
    hidden = policy.model_copy(
        update={"feedback_metrics": ("private_answer",), "selection_metric": "private_answer"}
    )
    with pytest.raises(ValueError, match="not explicitly released"):
        service.create(hidden, baseline)
    service.create(policy, baseline)
    with pytest.raises(ValueError, match="finished, released feedback"):
        service.propose(policy.campaign_id, "baseline", successor)

    def submit(*_):
        return {
            "run_id": "run-1",
            "attempt_id": "attempt-1",
            "state": "finished",
            "result": {
                "execution": "completed",
                "evaluation": "scored",
                "protocol": "valid",
                "cleanup_complete": True,
                "native_result": {"metrics": {"public_score": 0.4}},
            },
        }

    service.submit(policy.campaign_id, "baseline", submit)
    changed = successor.model_dump(mode="json")
    changed["frozen_plan"]["plan"]["request"]["candidate"]["judge"] = {
        "uri": "judge",
        "revision": "v1",
        "digest": "sha256:" + "0" * 64,
    }
    changed["frozen_plan"]["digest"] = canonical_digest(
        {key: value for key, value in changed["frozen_plan"].items() if key != "digest"}
    )
    changed["digest"] = canonical_digest(
        {key: value for key, value in changed.items() if key != "digest"}
    )
    with pytest.raises(ValueError, match="judge is outside authorized scope"):
        service.propose(
            policy.campaign_id,
            "baseline",
            PreparedExecution.model_validate_json(json.dumps(changed)),
        )


def test_lost_submission_reply_reuses_stable_operation_id(setup):
    service, baseline, _, policy, _ = setup
    service.create(policy, baseline)
    operations = []

    def submit(_, operation, group, limit):
        operations.append(operation)
        if len(operations) == 1:
            raise ConnectionError("reply lost")
        return {"run_id": "run-1", "attempt_id": "attempt-1", "state": "running"}

    with pytest.raises(ConnectionError):
        service.submit(policy.campaign_id, "baseline", submit)
    recovered = service.submit(policy.campaign_id, "baseline", submit)
    assert operations == [operations[0], operations[0]]
    assert recovered["candidates"][0]["run_id"] == "run-1"


def test_invalid_score_is_not_released_and_non_improvement_stops(setup):
    service, baseline, successor, policy, _ = setup
    service.create(policy, baseline)

    def outcome(score, protocol="valid"):
        return {
            "run_id": "run-" + str(score),
            "attempt_id": "attempt-" + str(score),
            "state": "finished",
            "result": {
                "execution": "completed",
                "evaluation": "scored",
                "protocol": protocol,
                "cleanup_complete": True,
                "native_result": {"metrics": {"public_score": score}},
            },
        }

    invalid = service.submit(policy.campaign_id, "baseline", lambda *_: outcome(0.8, "invalid"))
    assert invalid["candidates"][0]["score"] is None
    with pytest.raises(ValueError, match="finished, released feedback"):
        service.propose(policy.campaign_id, "baseline", successor)

    other = BenchmarkCampaignService(BenchmarkCampaignStore(setup[-1] / "other"))
    other.create(policy, baseline)
    other.submit(policy.campaign_id, "baseline", lambda *_: outcome(0.8))
    other.propose(policy.campaign_id, "baseline", successor)
    result = other.submit(policy.campaign_id, "revised", lambda *_: outcome(0.6))
    assert result["selected_candidate_id"] == "baseline"
    assert result["stop_reason"] == "no_improvement"


def test_campaign_cli_composition_creates_and_reads_private_state(setup):
    _, baseline, _, policy, root = setup
    execution_file = root / "baseline.json"
    write_execution(baseline, execution_file)
    policy_file = root / "policy.json"
    policy_file.write_text(policy.model_dump_json())
    base = {
        "benchmark_command": "campaign",
        "campaign_id": policy.campaign_id,
        "state_dir": str(root / "cli-state"),
        "config": None,
    }
    created = benchmark_action(
        argparse.Namespace(
            **base,
            campaign_command="create",
            policy=policy_file,
            execution=execution_file,
        )
    )
    assert created["candidates"][0]["candidate_id"] == "baseline"
    status = benchmark_action(argparse.Namespace(**base, campaign_command="status"))
    assert status == created
