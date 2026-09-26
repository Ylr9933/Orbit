"""Frozen batch membership and descriptive summaries, independent of scheduling."""

from collections import Counter
from typing import Any

from pydantic import Field, model_validator

from agent_infra.benchmarks.api import Contract, Digest
from agent_infra.benchmarks.planning import canonical_digest


class BatchMember(Contract):
    operation_id: str = Field(min_length=1)
    execution: str
    execution_digest: Digest
    unit_id: str


class BatchPlan(Contract):
    schema_version: int = 1
    members: tuple[BatchMember, ...] = Field(min_length=1)
    concurrency: int = Field(ge=1, le=64)
    model: str
    capability_scope: str = "operator_declared_not_runtime_attested"
    digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> "BatchPlan":
        if self.schema_version != 1:
            raise ValueError("unsupported batch schema")
        if len({m.operation_id for m in self.members}) != len(self.members):
            raise ValueError("duplicate batch operation ID")
        if len({m.execution for m in self.members}) != len(self.members):
            raise ValueError("duplicate execution file")
        if canonical_digest(self.model_dump(mode="json", exclude={"digest"})) != self.digest:
            raise ValueError("batch digest mismatch")
        return self


def summarize(batch: BatchPlan, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep missing/failed/unscored attempts visible; never manufacture a suite score."""
    by_operation = {run["operation_id"]: run for run in runs}
    rows = []
    for member in batch.members:
        run = by_operation.get(member.operation_id, {})
        result = run.get("result") or {}
        native = result.get("native_result") or {}
        rows.append(
            {
                "unit_id": member.unit_id,
                "operation_id": member.operation_id,
                "run_id": run.get("run_id"),
                "state": run.get("state", "not_submitted"),
                "execution": result.get("execution"),
                "evaluation": result.get("evaluation"),
                "protocol": result.get("protocol"),
                "metrics": native.get("metrics", {}),
                "artifact_id": result.get("artifact_id"),
                "cleanup_complete": result.get("cleanup_complete"),
                "failure_reason": native.get("failure_reason") or run.get("detail"),
            }
        )
    return {
        "batch_digest": batch.digest,
        "model": batch.model,
        "total": len(rows),
        "concurrency": batch.concurrency,
        "states": dict(Counter(row["state"] for row in rows)),
        "finished": sum(row["state"] == "finished" for row in rows),
        "scored": sum(row["evaluation"] == "scored" for row in rows),
        "failed": sum(row["execution"] == "failed" for row in rows),
        "cancelled": sum(row["execution"] == "cancelled" for row in rows),
        "official_score": None,
        "aggregation": "per-task results only; no substitute for native suite aggregation",
        "runs": rows,
    }
