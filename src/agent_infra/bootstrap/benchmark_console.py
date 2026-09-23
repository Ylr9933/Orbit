"""Read-only benchmark projection for the local administrator console."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_infra.benchmarks.compatibility import read_matrix
from agent_infra.projects.benchmark_campaign import BenchmarkCampaignService, BenchmarkCampaignStore
from agent_infra.resources.persistent import PersistentLeaseStore
from agent_infra.runs.control_store import RunControlStore


class BenchmarkConsole:
    def __init__(self, state_root: Path) -> None:
        self.root = state_root / "benchmarks"

    @staticmethod
    def _run(item: dict[str, Any]) -> dict[str, Any]:
        execution = item["request"]["execution"]
        plan = execution["frozen_plan"]["plan"]
        result = item.get("result") or {}
        accounting = result.get("resource_accounting") or {}
        return {
            "run_id": item["run_id"],
            "attempt_id": item["attempt_id"],
            "state": item["state"],
            "created_at": item["created_at"],
            "benchmark": plan["suite"]["benchmark"],
            "unit_id": plan["units"][0]["unit_id"],
            "candidate_id": plan["request"]["candidate"]["candidate_id"],
            "adapter": execution["frozen_plan"]["adapter"]["adapter_id"],
            "execution": result.get("execution"),
            "evaluation": result.get("evaluation"),
            "protocol": result.get("protocol"),
            "cleanup_complete": result.get("cleanup_complete"),
            "resources": {
                "requested": accounting.get("requested"),
                "authorized": accounting.get("authorized"),
                "actual_allocation": accounting.get("actual_allocation"),
                "usage": accounting.get("usage"),
            },
        }

    def snapshot(self) -> dict[str, Any]:
        control = self.root / "control.sqlite3"
        if not control.is_file():
            return {
                "available": False,
                "capacity": None,
                "active_leases": 0,
                "queued": 0,
                "runs": [],
                "campaigns": [],
                "compatibility": [],
            }
        store = RunControlStore(self.root, read_only=True)
        runs = store.list_runs(limit=50)
        lease_root = self.root / "leases"
        leases = (
            PersistentLeaseStore(lease_root, read_only=True)
            if (lease_root / "leases.sqlite3").is_file()
            else None
        )
        campaigns_root = self.root / "campaigns"
        campaigns = (
            BenchmarkCampaignService(
                BenchmarkCampaignStore(campaigns_root, read_only=True)
            ).list_campaigns()
            if (campaigns_root / "campaigns.sqlite3").is_file()
            else []
        )
        matrix_path = self.root / "compatibility.json"
        matrix = (
            read_matrix(matrix_path).model_dump(mode="json")["entries"]
            if matrix_path.is_file()
            else []
        )
        return {
            "available": True,
            "capacity": asdict(leases.capacity) if leases else None,
            "active_leases": sum(item.state.value != "released" for item in leases.list())
            if leases
            else 0,
            "queued": len(store.queued()),
            "runs": [self._run(item) for item in runs],
            "campaigns": campaigns,
            "compatibility": matrix,
        }
