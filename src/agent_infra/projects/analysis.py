"""Immutable interpretations of immutable, public execution evidence."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from agent_infra.projects._iteration_store import IterationStore
from agent_infra.projects.api import ProjectConflict, ProjectError
from agent_infra.projects.iteration_api import digest, document, identifier, items, pointer, text
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.research import ResearchService
from agent_infra.projects.research_api import ResearchDraft
from agent_infra.runs.query import RunQueries


class AnalysisService:
    def __init__(self, store: LocalProjectStore, queries: RunQueries) -> None:
        self.store, self.queries = store, queries
        self.research = ResearchService(store)
        self.documents = IterationStore(store.database)

    def evidence(self, project: str, reference: dict[str, Any]) -> dict[str, Any]:
        ref = document(
            reference,
            {"run_id", "artifact_id", "member", "metrics", "data_version", "code_version"},
            "result reference",
        )
        run = self.queries.status(text(ref.get("run_id"), "run_id"))
        if run["lineage"].get("project_id") != project:
            raise ProjectError("Run belongs to a different project")
        if run["state"] != "finished":
            raise ProjectError("finish the Run before recording an analysis")
        result: dict[str, Any] = {
            "run_id": run["run_id"],
            "outcome": run["result"],
            "lineage": run["lineage"],
            "data_version": ref.get("data_version"),
            "code_version": ref.get("code_version"),
            "version_source": "caller_declared; frozen task lineage retained separately",
            "metrics": [],
        }
        for key in ("data_version", "code_version"):
            if result[key] is not None:
                text(result[key], key)
        if not ref.get("artifact_id"):
            if ref.get("metrics") or ref.get("member"):
                raise ProjectError("metrics require an artifact and an exact member")
            return result  # Failure analysis without outputs is legitimate.
        artifact_id = text(ref["artifact_id"], "artifact_id")
        member = text(ref.get("member"), "member")
        artifact = self.queries.artifact(run["run_id"], artifact_id, member)
        raw = base64.b64decode(artifact["content_base64"], validate=True)
        result.update(
            artifact_id=artifact_id, member=member, content_sha256=hashlib.sha256(raw).hexdigest()
        )
        if ref.get("metrics"):
            if len(raw) > 1024**2:
                raise ProjectError("metric JSON exceeds 1 MiB")
            payload = json.loads(raw)
            for entry in items(ref["metrics"], "metrics"):
                metric = document(entry, {"name", "pointer", "unit", "direction"}, "metric")
                if metric.get("direction") not in {"maximize", "minimize", "inspect"}:
                    raise ProjectError("metric direction must be maximize, minimize or inspect")
                result["metrics"].append(
                    {
                        "name": text(metric.get("name"), "metric name"),
                        "unit": text(metric.get("unit"), "metric unit"),
                        "direction": metric["direction"],
                        "pointer": metric["pointer"],
                        "value": pointer(payload, metric["pointer"]),
                    }
                )
        return result

    def save(self, project: str, operation_id: str, value: dict[str, Any]) -> dict[str, Any]:
        self.research._project(project)
        identifier(operation_id)
        obj = document(
            value,
            {
                "results",
                "observations",
                "interpretation",
                "uncertainty",
                "recommendation",
                "supersedes",
            },
            "analysis",
        )
        key = digest({"project": project, "operation": operation_id})
        with self.store.writer():
            try:
                old = self.documents.get(project, "analysis", key)
                if old["request"] != obj:
                    raise ProjectConflict("analysis operation already has different content")
                return old
            except KeyError:
                pass
            if obj.get("supersedes"):
                self.documents.get(project, "analysis", obj["supersedes"])
            references = [
                self.evidence(project, ref) for ref in items(obj.get("results"), "results")
            ]
            prose = {
                field: text(obj.get(field), field)
                for field in ("observations", "interpretation", "uncertainty", "recommendation")
            }
            saved = {
                "analysis_id": key,
                "project_id": project,
                "created_at": datetime.now(UTC).isoformat(),
                "request": obj,
                "evidence": references,
                **prose,
                "scientific_truth_verified": False,
                "comparison": self.compare(references),
            }
            self.documents.put(project, "analysis", key, saved)
            return saved

    @staticmethod
    def compare(results: list[dict[str, Any]]) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            # No cross-data ranking, no implicit promotion of failed executions.
            if not result["data_version"] or (result["outcome"] or {}).get("status") not in {
                "succeeded",
                "completed",
            }:
                continue
            for metric in result["metrics"]:
                key = digest(
                    [metric["name"], metric["unit"], metric["direction"], result["data_version"]]
                )
                groups.setdefault(key, []).append({"run_id": result["run_id"], **metric})
        return {
            "groups": list(groups.values()),
            "ranked": False,
            "note": "Matching data/unit/direction; protocol equivalence unverified.",
        }

    def decide(self, project: str, operation_id: str, value: dict[str, Any]) -> dict[str, Any]:
        obj = document(
            value,
            {
                "analysis_id",
                "choice",
                "reason",
                "authorization",
                "expected_revision",
                "expected_digest",
                "draft",
            },
            "decision",
        )
        identifier(operation_id)
        choice = obj.get("choice")
        if choice not in {"accept", "modify", "reject"}:
            raise ProjectError("choice must be accept, modify or reject")
        text(obj.get("reason"), "reason")
        text(obj.get("authorization"), "user authorization source")
        key = digest({"project": project, "operation": operation_id})
        with self.store.writer():
            self.documents.get(project, "analysis", obj["analysis_id"])
            try:
                saved = self.documents.get(project, "decision", key)
                if saved["request"] != obj:
                    raise ProjectConflict("decision operation changed")
                if saved["state"] == "completed":
                    return saved
            except KeyError:
                latest = self.research.show(project)["research"]
                if not latest or (latest["revision"], latest["digest"]) != (
                    obj.get("expected_revision"),
                    obj.get("expected_digest"),
                ):
                    raise ProjectConflict(
                        "stale decision; reload the exact research revision"
                    ) from None
                if choice == "reject" and obj.get("draft") is not None:
                    raise ProjectError("rejection must not include a replacement draft") from None
                if choice != "reject":
                    proposed = ResearchDraft.from_dict(obj["draft"]).to_dict()
                    if proposed["brief"] != latest["document"]["brief"]:
                        raise ProjectError(
                            "iteration cannot change the brief; revise explicitly first"
                        ) from None
                    previous = {e["id"] for e in latest["document"]["plan"]["experiments"]}
                    if not any(e["id"] not in previous for e in proposed["plan"]["experiments"]):
                        raise ProjectError("a next plan requires a new experiment ID") from None
                saved = {
                    "decision_id": key,
                    "request": obj,
                    "state": "applying",
                    "created_at": datetime.now(UTC).isoformat(),
                }
                self.documents.put(project, "decision", key, saved)
            if choice != "reject":
                # A durable decision precedes the idempotent B save/confirm steps. A lost reply
                # resumes these exact steps, never invents another revision or starts a Run.
                draft = ResearchDraft.from_dict(obj["draft"])
                result = self.research._save(
                    self.research._project(project),
                    draft,
                    obj["expected_revision"],
                    f"iteration decision {key}; analysis {obj['analysis_id']}",
                )
                revision = result["research"]
                self.store.confirm_research(
                    project,
                    revision=revision["revision"],
                    digest=revision["digest"],
                    decision=f"{obj['authorization']}: {obj['reason']}",
                )
                saved["research"] = revision
            saved["state"] = "completed"
            self.documents.put(project, "decision", key, saved)
            return saved

    def list(self, project: str, kind: str) -> dict[str, Any]:
        self.research._project(project)
        if kind not in {"analysis", "decision"}:
            raise ProjectError("unknown result kind")
        return {"items": self.documents.list(project, kind)}
