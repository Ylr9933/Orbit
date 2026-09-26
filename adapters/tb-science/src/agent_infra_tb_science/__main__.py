"""Offline suite inventory: report every task, including rejected profiles."""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from agent_infra.benchmarks.api import PlanRequest

from . import Adapter, task_config


def audit(source: Path, request: PlanRequest) -> dict:
    adapter = Adapter()
    rows = []
    for path in sorted(source.resolve().rglob("task.toml")):
        row = {"path": str(path.parent), "eligible": False}
        try:
            config = task_config(path.parent)
            row["declared_solver_resources"] = config.get("environment", {})
            row["declared_verifier_resources"] = config.get("verifier", {}).get("environment", {})
            catalog = adapter.discover(path.parent)
            selected = request.model_copy(update={"selection": (catalog.units[0].unit_id,)})
            plan = adapter.plan(catalog, selected)
            issues = adapter.validate(plan)
            row.update(
                unit_id=catalog.units[0].unit_id,
                resources=plan.phases[0].resources.model_dump(mode="json"),
                budget=plan.phases[0].budget.model_dump(mode="json"),
                eligible=not issues,
                issues=[i.model_dump(mode="json") for i in issues],
            )
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            row["issues"] = [{"message": str(error)[:200]}]
        rows.append(row)
    return {
        "scope": "offline profile eligibility; not runtime/model attestation",
        "total": len(rows),
        "eligible": sum(r["eligible"] for r in rows),
        "rejection_reasons": dict(
            Counter(i["message"] for r in rows if not r["eligible"] for i in r["issues"])
        ),
        "tasks": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new audit file")
    request = PlanRequest.model_validate_json(args.request.read_bytes())
    result = audit(args.source, request)
    if not result["total"]:
        raise ValueError("no task.toml found")
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "tasks"}))


if __name__ == "__main__":
    main()
