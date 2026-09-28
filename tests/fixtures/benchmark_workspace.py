"""Explicit synthetic batches for console tests; never launches a process or model."""

import json
from datetime import UTC, datetime
from pathlib import Path

from agent_infra.benchmarks.api import (
    AdapterIdentity,
    Budget,
    CandidateRef,
    ExecutionPlan,
    Phase,
    PinnedSource,
    PlanRequest,
    RetryPolicy,
    SuiteRef,
    WorkUnit,
)
from agent_infra.benchmarks.execution import PreparedExecution
from agent_infra.benchmarks.execution_api import NativeInvocation
from agent_infra.benchmarks.planning import FrozenPlan, SourceSnapshot, canonical_digest
from agent_infra.environments.api import ProcessCommand
from agent_infra.records.api import (
    AttemptManifest,
    ProducerKind,
    RecordContext,
    RunManifest,
    Visibility,
)
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.control_store import RunControlStore

DIGEST = "sha256:" + "1" * 64


def execution(unit: str, candidate: str) -> PreparedExecution:
    source = PinnedSource(uri="urn:synthetic:test", revision="test-v1", digest=DIGEST)
    request = PlanRequest(
        selection=(unit,),
        candidate=CandidateRef(
            candidate_id=candidate,
            agent="fixture-agent",
            agent_version="1",
            model=candidate,
            configuration_digest=DIGEST,
        ),
    )
    plan = ExecutionPlan(
        suite=SuiteRef(
            benchmark="synthetic-web",
            profile="test-v1",
            synthetic=True,
            source=source,
            runner=source,
        ),
        request=request,
        retry=RetryPolicy(owner="none", max_attempts=1),
        units=(WorkUnit(unit_id=unit, native_id=unit, kind="single"),),
        phases=(
            Phase(
                phase_id="native",
                kind="evaluate",
                owner="native",
                backend="fixture",
                budget=Budget(wall_seconds=60, clock="outer_wall_clock"),
            ),
        ),
    )
    frozen = FrozenPlan(
        adapter=AdapterIdentity(
            distribution="fixture",
            version="1",
            entry_point="fixture",
            adapter_id="fixture",
            sdk_version="1.0",
        ),
        source=SourceSnapshot(path="/unused-fixture", digest=DIGEST),
        catalog_digest=DIGEST,
        plan=plan,
        digest=DIGEST,
    )
    frozen = frozen.model_copy(
        update={"digest": canonical_digest(frozen.model_dump(mode="json", exclude={"digest"}))}
    )
    value = PreparedExecution(
        frozen_plan=frozen,
        invocation=NativeInvocation(command=ProcessCommand(argv=("false",))),
        digest=DIGEST,
    )
    return value.model_copy(
        update={"digest": canonical_digest(value.model_dump(mode="json", exclude={"digest"}))}
    )


def make_batch(root: Path, candidate: str, count: int = 60, *, incomplete: bool = False) -> dict:
    root.mkdir(parents=True)
    store = RunControlStore(root / "state/benchmarks")
    records = LocalRecordsStore(root / "state/benchmarks/records")
    members, runs = [], []
    for i in range(count):
        unit = f"task-{i:03}"
        prepared = execution(unit, candidate)
        file = f"execution-{i}.json"
        (root / file).write_text(prepared.model_dump_json())
        op = f"{candidate}-{i}"
        members.append(
            {
                "operation_id": op,
                "execution": file,
                "execution_digest": prepared.digest,
                "unit_id": unit,
            }
        )
        if incomplete and i == count - 1:
            continue
        run = store.create(
            op,
            {"kind": "benchmark", "execution": prepared.model_dump(mode="json")},
            {},
            initial_state="queued",
            launch_authorized=True,
        )
        native = {
            "metrics": {"score": float(i + (2 if candidate == "revised" else 0))},
            "private_answer": "PRIVATE_NATIVE_SENTINEL",
        }
        result = {
            "execution": "completed",
            "evaluation": "scored",
            "protocol": "valid",
            "cleanup_complete": True,
            "native_result": native,
            "resource_accounting": {"usage": {"elapsed_seconds": 20.0}},
        }
        if incomplete and i == count - 2:
            result.update(execution="failed", evaluation="failed")
            native["failure_reason"] = "synthetic model unavailable"
        if i == 0:
            now = datetime.now(UTC)
            records.begin_run(RunManifest(run["run_id"], now, {}))
            records.begin_attempt(AttemptManifest(run["attempt_id"], run["run_id"], now))
            sink = records.scoped_sink(
                RecordContext(run["run_id"], run["attempt_id"], "fixture", ProducerKind.RUN)
            )
            artifact = root / "artifact"
            evidence = artifact / "outputs/evidence"
            evidence.mkdir(parents=True)
            steps = [
                {
                    "step_index": step,
                    "step_type": "tool_call" if step % 2 == 0 else "tool_result",
                    "content": f"{'python analysis.py' if step % 2 == 0 else 'result'} step {step}",
                    "metadata": {
                        "tool_name": "shell",
                        "tool_call_id": str(step // 2),
                        **({"exit_code": 1, "is_error": True} if step == 57 else {}),
                    },
                }
                for step in range(120)
            ]
            steps[57]["content"] = "DEEP_ERROR: missing column"
            (evidence / "trajectory.json").write_text(json.dumps(steps))
            (evidence / "trajectory-view.json").write_text(json.dumps(steps[:2]))
            (artifact / "outputs/score.json").write_text('{"score": 0}')
            (artifact / "outputs/benchflow_score.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "gate_results": [],
                        "score_details": [{"details": {"nested": {"evaluator_unavailable": True}}}],
                        "hard_gates_passed": True,
                    }
                )
            )
            (evidence / "codex-stdout.jsonl").write_text(
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {"message": "You've hit your usage limit"},
                    }
                )
                + "\n"
            )
            native_root = artifact / "outputs/native" / unit
            native_root.mkdir(parents=True)
            (native_root / (unit + "__b3.json")).write_text('{"status": "timeout"}')
            ref = sink.commit_artifact(
                artifact, name="native-submission", visibility=Visibility.ADMIN
            )
            result["artifact_id"] = ref.artifact_id
            native["evidence"] = {
                "capture_status": "complete",
                "trajectory": {
                    "capture_status": "complete",
                    "total_steps": 120,
                    "member": "outputs/evidence/trajectory-view.json",
                    "origin": "synthetic-test",
                },
            }
        run = store.update(run["run_id"], state="finished", result=result)
        runs.append(run)
    body = {
        "schema_version": 1,
        "members": members,
        "concurrency": 2,
        "model": candidate,
        "capability_scope": "operator_declared_not_runtime_attested",
    }
    (root / "batch.json").write_text(json.dumps({**body, "digest": canonical_digest(body)}))
    return {"root": root, "runs": runs, "store": store}
