"""Durable outer-campaign decisions; native trials remain owned by BenchmarkExecutionService."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from agent_infra.benchmarks.campaign_api import CampaignPolicy
from agent_infra.benchmarks.execution import PreparedExecution
from agent_infra.benchmarks.planning import canonical_digest


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _operation_id(campaign_id: str, candidate_id: str) -> str:
    digest = hashlib.sha256(f"{campaign_id}\0{candidate_id}".encode()).hexdigest()
    return "bm06-" + digest


def _budget_group(campaign_id: str) -> str:
    return "bm06-" + hashlib.sha256(campaign_id.encode()).hexdigest()


def _metric_value(value: object) -> float | None:
    if type(value) not in {int, float}:
        return None
    try:
        number = float(cast(int | float, value))
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _released_metrics(execution: PreparedExecution, policy: CampaignPolicy) -> None:
    frozen = execution.frozen_plan
    if canonical_digest(frozen.model_dump(mode="json", exclude={"digest"})) != frozen.digest:
        raise ValueError("campaign plan digest mismatch")
    if canonical_digest(execution.model_dump(mode="json", exclude={"digest"})) != execution.digest:
        raise ValueError("campaign execution digest mismatch")
    allowed: set[str] = set()
    for rule in execution.frozen_plan.plan.feedback:
        if rule.recipient == "optimizer" and rule.release in {"during_trial", "after_trial"}:
            allowed.update(rule.fields)
    if set(policy.feedback_metrics) - allowed:
        raise ValueError("campaign metric is not explicitly released to the optimizer")


def _compare_execution(
    baseline: PreparedExecution, successor: PreparedExecution, policy: CampaignPolicy
) -> list[str]:
    left, right = baseline.frozen_plan, successor.frozen_plan
    if (
        left.adapter != right.adapter
        or left.source != right.source
        or left.catalog_digest != right.catalog_digest
    ):
        raise ValueError("candidate changed adapter, source or catalog")
    base_plan, new_plan = left.plan, right.plan
    if base_plan.model_copy(update={"request": new_plan.request}) != new_plan:
        raise ValueError("candidate changed suite, protocol, units, phases, retry or feedback")
    base_request, new_request = base_plan.request, new_plan.request
    if base_request.selection != new_request.selection:
        raise ValueError("candidate changed benchmark unit selection")
    old, new = base_request.candidate, new_request.candidate
    if old.candidate_id == new.candidate_id:
        raise ValueError("successor requires a new candidate_id")
    changed: list[str] = []
    for field in (
        "agent",
        "agent_version",
        "model",
        "configuration_digest",
        "target_model",
        "judge",
    ):
        if getattr(old, field) != getattr(new, field):
            if field not in policy.allowed_candidate_fields:
                raise ValueError(f"candidate field {field} is outside authorized scope")
            changed.append("candidate." + field)
    old_params = {item.key: item.value for item in base_request.parameters}
    new_params = {item.key: item.value for item in new_request.parameters}
    for key in sorted(old_params.keys() | new_params.keys()):
        if old_params.get(key) != new_params.get(key):
            if key not in policy.allowed_parameter_keys:
                raise ValueError(f"parameter {key} is outside authorized scope")
            changed.append("parameters." + key)
    if not changed:
        raise ValueError("successor must change an authorized field")
    return changed


class BenchmarkCampaignStore:
    """One SQLite document per campaign; a file lock serializes external Run submission intent."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "campaigns.sqlite3"
        with closing(self._connect()) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS campaigns "
                "(campaign_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            db.commit()
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        fd = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def get(self, campaign_id: str) -> dict[str, Any]:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT document FROM campaigns WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        return dict(json.loads(row[0]))

    def create(self, campaign_id: str, document: dict[str, Any]) -> None:
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO campaigns VALUES (?,?)",
                (campaign_id, json.dumps(document, sort_keys=True, allow_nan=False)),
            )
            db.commit()

    def save(self, campaign_id: str, document: dict[str, Any]) -> None:
        document["updated_at"] = _now()
        with closing(self._connect()) as db:
            db.execute(
                "UPDATE campaigns SET document=? WHERE campaign_id=?",
                (json.dumps(document, sort_keys=True, allow_nan=False), campaign_id),
            )
            db.commit()


class BenchmarkCampaignService:
    def __init__(self, store: BenchmarkCampaignStore) -> None:
        self.store = store

    def create(self, policy: CampaignPolicy, baseline: PreparedExecution) -> dict[str, Any]:
        _released_metrics(baseline, policy)
        candidate_id = baseline.frozen_plan.plan.request.candidate.candidate_id
        with self.store.exclusive():
            document: dict[str, Any] = {
                "campaign_id": policy.campaign_id,
                "policy": policy.model_dump(mode="json"),
                "candidates": [self._candidate(baseline, None, None, None, [])],
                "state": "active",
                "stop_reason": None,
                "selected_candidate_id": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.store.create(policy.campaign_id, document)
            assert document["candidates"][0]["candidate_id"] == candidate_id
            return self._view(document)

    @staticmethod
    def _candidate(
        execution: PreparedExecution,
        parent_id: str | None,
        based_on_run_id: str | None,
        based_on_feedback: dict[str, float] | None,
        changes: list[str],
    ) -> dict[str, Any]:
        return {
            "candidate_id": execution.frozen_plan.plan.request.candidate.candidate_id,
            "execution": execution.model_dump(mode="json"),
            "execution_digest": execution.digest,
            "parent_id": parent_id,
            "based_on_run_id": based_on_run_id,
            "based_on_feedback": based_on_feedback,
            "changes": changes,
            "operation_id": None,
            "run_id": None,
            "attempt_id": None,
            "state": "prepared",
            "feedback": None,
            "score": None,
            "outcome": None,
        }

    def propose(
        self, campaign_id: str, parent_id: str, successor: PreparedExecution
    ) -> dict[str, Any]:
        with self.store.exclusive():
            document = self.store.get(campaign_id)
            policy = CampaignPolicy.model_validate_json(json.dumps(document["policy"]))
            if document["state"] != "active":
                raise ValueError("campaign has stopped")
            if len(document["candidates"]) >= policy.max_trials:
                raise ValueError("campaign trial limit reached")
            if any(
                item["candidate_id"] == successor.frozen_plan.plan.request.candidate.candidate_id
                for item in document["candidates"]
            ):
                raise ValueError("candidate_id already exists")
            parent = next(
                (item for item in document["candidates"] if item["candidate_id"] == parent_id),
                None,
            )
            if parent is None or parent["state"] != "finished" or parent["score"] is None:
                raise ValueError("parent requires finished, released feedback")
            baseline = PreparedExecution.model_validate_json(
                json.dumps(document["candidates"][0]["execution"])
            )
            _released_metrics(successor, policy)
            changes = _compare_execution(baseline, successor, policy)
            document["candidates"].append(
                self._candidate(
                    successor, parent_id, parent["run_id"], dict(parent["feedback"]), changes
                )
            )
            self.store.save(campaign_id, document)
            return self._view(document)

    def submit(
        self,
        campaign_id: str,
        candidate_id: str,
        submitter: Callable[[PreparedExecution, str, str, float], dict[str, Any]],
    ) -> dict[str, Any]:
        with self.store.exclusive():
            document = self.store.get(campaign_id)
            policy = CampaignPolicy.model_validate_json(json.dumps(document["policy"]))
            if document["state"] != "active":
                raise ValueError("campaign has stopped")
            candidate = next(
                (item for item in document["candidates"] if item["candidate_id"] == candidate_id),
                None,
            )
            if candidate is None:
                raise KeyError(candidate_id)
            if candidate["state"] not in {"prepared", "submitting"}:
                return self._view(document)
            if (
                candidate is not document["candidates"][0]
                and document["candidates"][-1] is not candidate
            ):
                raise ValueError("submit the newest successor; prior candidate is immutable")
            candidate["operation_id"] = _operation_id(campaign_id, candidate_id)
            candidate["state"] = "submitting"
            self.store.save(campaign_id, document)
            run = submitter(
                PreparedExecution.model_validate_json(json.dumps(candidate["execution"])),
                candidate["operation_id"],
                _budget_group(campaign_id),
                float(policy.max_wall_seconds),
            )
            candidate["run_id"] = run["run_id"]
            candidate["attempt_id"] = run["attempt_id"]
            candidate["state"] = "running"
            self._observe(candidate, run, policy)
            self._select(document, policy)
            self.store.save(campaign_id, document)
            return self._view(document)

    def refresh(self, campaign_id: str, status: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
        with self.store.exclusive():
            document = self.store.get(campaign_id)
            before = json.dumps(document, sort_keys=True)
            policy = CampaignPolicy.model_validate_json(json.dumps(document["policy"]))
            for candidate in document["candidates"]:
                if candidate["run_id"] and candidate["state"] != "finished":
                    self._observe(candidate, status(candidate["run_id"]), policy)
            self._select(document, policy)
            if json.dumps(document, sort_keys=True) != before:
                self.store.save(campaign_id, document)
            return self._view(document)

    @staticmethod
    def _observe(candidate: dict[str, Any], run: dict[str, Any], policy: CampaignPolicy) -> None:
        if run["state"] != "finished":
            candidate["state"] = "running"
            return
        result = run.get("result") or {}
        native = result.get("native_result") or {}
        candidate["state"] = "finished"
        candidate["outcome"] = {
            "execution": result.get("execution"),
            "evaluation": result.get("evaluation"),
            "protocol": result.get("protocol"),
            "capture": result.get("capture"),
            "cleanup_complete": result.get("cleanup_complete"),
        }
        if (
            result.get("execution") == "completed"
            and result.get("evaluation") == "scored"
            and result.get("protocol") == "valid"
            and result.get("cleanup_complete") is True
        ):
            metrics = native.get("metrics") or {}
            if isinstance(metrics, dict):
                candidate["feedback"] = {
                    key: number
                    for key in policy.feedback_metrics
                    if (number := _metric_value(metrics.get(key))) is not None
                }
                candidate["score"] = candidate["feedback"].get(policy.selection_metric)

    @staticmethod
    def _select(document: dict[str, Any], policy: CampaignPolicy) -> None:
        candidates = document["candidates"]
        best: dict[str, Any] | None = None
        for item in candidates:
            if item["score"] is None:
                continue
            if best is None or (
                item["score"] > best["score"]
                if policy.direction == "maximize"
                else item["score"] < best["score"]
            ):
                best = item
        document["selected_candidate_id"] = best["candidate_id"] if best else None
        if document["state"] != "active":
            return
        if len(candidates) >= 2 and candidates[-1]["state"] == "finished":
            previous = next(
                (
                    item
                    for item in candidates[:-1]
                    if item["candidate_id"] == candidates[-1]["parent_id"]
                ),
                None,
            )
            last = candidates[-1]
            if previous is not None and previous["score"] is not None:
                gain = None
                if last["score"] is not None:
                    gain = last["score"] - previous["score"]
                    if policy.direction == "minimize":
                        gain = -gain
                if gain is None or gain <= policy.minimum_improvement:
                    document["state"] = "stopped"
                    document["stop_reason"] = "no_improvement"
        if (
            all(item["state"] == "finished" for item in candidates)
            and len(candidates) >= policy.max_trials
        ):
            document["state"] = "stopped"
            document["stop_reason"] = document["stop_reason"] or "trial_limit"

    def stop(self, campaign_id: str) -> dict[str, Any]:
        with self.store.exclusive():
            document = self.store.get(campaign_id)
            if any(item["state"] in {"running", "submitting"} for item in document["candidates"]):
                raise ValueError("finish or cancel active trials before stopping campaign")
            document["state"] = "stopped"
            document["stop_reason"] = "operator"
            self.store.save(campaign_id, document)
            return self._view(document)

    @staticmethod
    def _view(document: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in document.items() if key != "candidates"} | {
            "candidates": [
                {key: value for key, value in item.items() if key not in {"execution", "outcome"}}
                for item in document["candidates"]
            ]
        }
