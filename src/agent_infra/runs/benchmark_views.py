"""Pure administrator projections of durable benchmark state; no runtime actions."""

import hashlib
import json
import math
from collections import Counter
from typing import Any


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def project_run(item: dict[str, Any]) -> dict[str, Any]:
    execution = item["request"]["execution"]
    frozen = execution["frozen_plan"]
    plan = frozen["plan"]
    suite = plan["suite"]
    candidate = plan["request"]["candidate"]
    result = item.get("result") or {}
    native = result.get("native_result") or {}
    accounting = result.get("resource_accounting") or {}
    phase = plan["phases"][0]
    params = {p["key"]: p["value"] for p in plan["request"].get("parameters", [])}
    usage = accounting.get("usage") or item.get("usage") or {}
    metrics = {
        key: value
        for key, value in native.get("metrics", {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    }
    valid = (
        bool(metrics) and result.get("evaluation") == "scored" and result.get("protocol") == "valid"
    )
    return {
        "run_id": item["run_id"],
        "attempt_id": item["attempt_id"],
        "operation_id": item["operation_id"],
        "state": item["state"],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "benchmark": suite["benchmark"],
        "unit_id": plan["units"][0]["unit_id"],
        "candidate_id": candidate["candidate_id"],
        "model": candidate["model"],
        "agent": candidate["agent"],
        "adapter": frozen["adapter"]["adapter_id"],
        "execution": result.get("execution"),
        "evaluation": result.get("evaluation"),
        "protocol": result.get("protocol"),
        "cleanup_complete": result.get("cleanup_complete"),
        "metrics": metrics,
        "score_valid": valid,
        "failure_reason": native.get("failure_reason") or item.get("detail"),
        "cancel_requested": item.get("cancel_requested", False),
        "elapsed_seconds": usage.get("elapsed_seconds"),
        "budget_seconds": phase.get("budget", {}).get("wall_seconds"),
        "config": {
            "candidate": candidate,
            "parameters": params,
            "resources": phase.get("resources"),
            "budget": phase.get("budget"),
            "adapter": frozen["adapter"],
            "suite": suite,
        },
        "comparison_key": digest(
            {
                "benchmark": suite["benchmark"],
                "profile": suite.get("profile"),
                "source": suite.get("source", {}).get("digest"),
                "dataset": (suite.get("dataset") or {}).get("digest"),
                "runner": suite.get("runner", {}).get("digest"),
                "units": plan["units"],
                "materials": [
                    (m.get("material_id"), m.get("source", {}).get("digest"))
                    for m in phase.get("materials", [])
                ],
            }
        ),
        "resources": {
            "requested": accounting.get("requested"),
            "authorized": accounting.get("authorized"),
            "actual_allocation": accounting.get("actual_allocation"),
            "usage": usage,
        },
        "has_evidence": bool(result.get("artifact_id")),
        "evidence_id": result.get("artifact_id"),
        "execution_digest": execution.get("digest"),
    }


def summarize_runs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[float]] = {}
    for row in rows:
        if row.get("score_valid"):
            for metric, value in row["metrics"].items():
                values.setdefault(metric, []).append(value)
    return {
        "health": {
            "needs_review": sum(
                r.get("health", {}).get("evaluation", {}).get("status") == "needs_review"
                for r in rows
            ),
            "unknown": sum(
                r.get("health", {}).get("evaluation", {}).get("status", "unknown") == "unknown"
                for r in rows
            ),
            "solver_failed": sum(
                r.get("health", {}).get("solver", {}).get("status") in {"failed", "quota_exhausted"}
                for r in rows
            ),
            "status_conflicts": sum(
                bool(r.get("health", {}).get("solver", {}).get("status_conflict")) for r in rows
            ),
        },
        "total": len(rows),
        "states": dict(Counter(row["state"] for row in rows)),
        "finished": sum(row["state"] == "finished" for row in rows),
        "scored": sum(bool(row.get("score_valid")) for row in rows),
        "failed": sum(row.get("execution") in {"failed", "timed_out"} for row in rows),
        "duplicate_tasks": len(rows) != len({r["unit_id"] for r in rows}),
        "cohort": digest(sorted(r["comparison_key"] for r in rows)),
        "metrics": {
            key: {"mean": sum(items) / len(items), "count": len(items)}
            for key, items in values.items()
        },
        "updated_at": max((r.get("updated_at", "") for r in rows), default=""),
        "created_at": min((r.get("created_at", "") for r in rows), default=""),
    }


def compare_runs(
    left: list[dict[str, Any]], right: list[dict[str, Any]], metric: str
) -> dict[str, Any]:
    """Compare exact tasks/protocols. Duplicates and missing scores never become zero."""

    def index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(row["unit_id"], []).append(row)
        return result

    a, b = index(left), index(right)
    rows: list[dict[str, Any]] = []
    for unit in sorted(a.keys() | b.keys()):
        aa, bb = a.get(unit, []), b.get(unit, [])
        baseline, r = (aa[0] if len(aa) == 1 else None), (bb[0] if len(bb) == 1 else None)
        reason = None
        if len(aa) > 1 or len(bb) > 1:
            reason = "同一批次有多次尝试，请选择单次实验批次"
        elif not baseline or not r:
            reason = "仅一侧包含该任务"
        elif baseline["comparison_key"] != r["comparison_key"]:
            reason = "任务材料或评分协议版本不同"
        elif not all(
            x.get("score_valid") and metric in x.get("metrics", {}) for x in (baseline, r)
        ):
            reason = "缺少有效评分"
        lv = baseline.get("metrics", {}).get(metric) if baseline else None
        rv = r.get("metrics", {}).get(metric) if r else None
        rows.append(
            {
                "unit_id": unit,
                "left": baseline,
                "right": r,
                "reason": reason,
                "delta": float(rv) - float(lv)
                if reason is None and rv is not None and lv is not None
                else None,
            }
        )
    paired = [r for r in rows if r["delta"] is not None]
    return {
        "metric": metric,
        "rows": rows,
        "paired": len(paired),
        "total": len(rows),
        "left_mean": sum(r["left"]["metrics"][metric] for r in paired) / len(paired)
        if paired
        else None,
        "right_mean": sum(r["right"]["metrics"][metric] for r in paired) / len(paired)
        if paired
        else None,
        "mean_delta": sum(r["delta"] for r in paired) / len(paired) if paired else None,
        "aggregation": "同任务有效评分交集的描述性均值；不是原生套件或官方总分",
    }
