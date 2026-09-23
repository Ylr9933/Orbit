"""Conservative wall-time reservations and charges for a benchmark budget group."""

from __future__ import annotations

from typing import Any


def reservation(run: dict[str, Any]) -> float:
    phase = run["request"]["execution"]["frozen_plan"]["plan"]["phases"][0]
    budget = phase["budget"].get("wall_seconds")
    if budget is None:
        budget = run["request"]["execution"]["invocation"]["command"]["timeout_seconds"]
    return float(budget)


def charge(run: dict[str, Any]) -> float:
    if run["state"] != "finished":
        return reservation(run)
    result = run.get("result") or {}
    if result.get("cleanup_scope") == "never_launched":
        return 0.0
    usage = (result.get("resource_accounting") or {}).get("usage") or {}
    elapsed = usage.get("elapsed_seconds")
    # A missing terminal measurement is charged at the full reservation, never at zero.
    return max(0.0, float(elapsed)) if elapsed is not None else reservation(run)


def budget_view(run: dict[str, Any], ordered: list[dict[str, Any]]) -> dict[str, Any] | None:
    group = run["request"].get("budget_group")
    if group is None:
        return None
    limit = float(run["request"]["budget_wall_seconds"])
    prior = 0.0
    for item in ordered:
        if item["run_id"] == run["run_id"]:
            break
        if item["request"].get("budget_group") != group:
            continue
        if float(item["request"]["budget_wall_seconds"]) != limit:
            raise ValueError("budget group has conflicting limits")
        prior += charge(item)
    return {
        "group": group,
        "limit_wall_seconds": limit,
        "prior_charged_or_reserved_seconds": prior,
        "reserved_seconds": reservation(run),
        "admissible": prior + reservation(run) <= limit,
    }
