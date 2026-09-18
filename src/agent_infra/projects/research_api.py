"""Versioned research drafts. Missing research details are legal; malformed data is not."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from agent_infra.contracts.files import relative_path
from agent_infra.projects.api import ProjectError, require_text


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectError(f"duplicate research JSON key: {key}")
        result[key] = value
    return result


def _object(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(key not in keys for key in value):
        raise ProjectError(f"{field} must be an object with only: {', '.join(sorted(keys))}")
    return value


def _text(value: Any, field: str, *, empty: bool = True) -> str:
    if empty and value == "":
        return ""
    require_text(value, field, 20_000)
    return str(value)


def _list(value: Any, field: str, limit: int = 100) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise ProjectError(f"{field} must be a list of at most {limit} items")
    return value


def _texts(value: Any, field: str) -> list[str]:
    return [_text(item, field, empty=False) for item in _list(value, field)]


def _path(value: Any, field: str) -> str:
    result = _text(value, field, empty=False)
    relative_path(result)
    return result


def _claim(value: Any) -> dict[str, Any]:
    obj = _object(value, {"text", "origin", "references"}, "claim")
    origin = obj.get("origin")
    if origin not in ("user", "sourced", "inference", "assumption"):
        raise ProjectError("claim.origin must be user, sourced, inference or assumption")
    references = _texts(obj.get("references", []), "claim.references")
    if origin == "sourced" and not references:
        raise ProjectError("sourced claims require references; references do not prove truth")
    for reference in references:
        if reference.startswith(("https://", "http://")):
            if not urlsplit(reference).hostname:
                raise ProjectError("source URL requires a hostname")
        else:
            _path(reference, "claim.references")
    return {
        "text": _text(obj.get("text"), "claim.text", empty=False),
        "origin": origin,
        "references": references,
    }


def _experiment(value: Any) -> dict[str, Any]:
    text_fields = {"title", "hypothesis", "method", "controls", "variables", "stopping_condition"}
    obj = _object(
        value,
        text_fields | {"id", "inputs", "metrics", "outputs", "resource_request"},
        "experiment",
    )
    identifier = obj.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", identifier
    ):
        raise ProjectError("experiment.id must be a stable identifier (1–80 letters/digits/_/-)")
    result: dict[str, Any] = {"id": identifier}
    result.update(
        {key: _text(obj.get(key, ""), f"experiment.{key}") for key in sorted(text_fields)}
    )
    inputs = []
    for item in _list(obj.get("inputs", []), "experiment.inputs"):
        entry = _object(item, {"path", "description", "version"}, "input")
        inputs.append(
            {
                "path": _path(entry.get("path"), "input.path"),
                "description": _text(entry.get("description", ""), "input.description"),
                "version": _text(entry.get("version", ""), "input.version"),
            }
        )
    metrics = []
    for item in _list(obj.get("metrics", []), "experiment.metrics"):
        entry = _object(item, {"name", "direction"}, "metric")
        direction = entry.get("direction")
        if direction not in ("maximize", "minimize", "inspect"):
            raise ProjectError("metric.direction must be maximize, minimize or inspect")
        metrics.append(
            {"name": _text(entry.get("name"), "metric.name", empty=False), "direction": direction}
        )
    result.update(
        inputs=inputs,
        metrics=metrics,
        outputs=[_path(p, "experiment.outputs") for p in _list(obj.get("outputs", []), "outputs")],
        resource_request=None
        if obj.get("resource_request") is None
        else _path(obj["resource_request"], "experiment.resource_request"),
    )
    return result


def _normalize(value: Any) -> dict[str, Any]:
    obj = _object(value, {"schema_version", "brief", "plan", "claims", "next_step"}, "research")
    if type(obj.get("schema_version")) is not int or obj["schema_version"] != 1:
        raise ProjectError("research schema_version must be 1")
    brief = _object(
        obj.get("brief", {}),
        {"question", "background", "success_criteria", "constraints", "unknowns"},
        "brief",
    )
    plan = _object(obj.get("plan", {}), {"summary", "experiments"}, "plan")
    experiments = [
        _experiment(item) for item in _list(plan.get("experiments", []), "experiments", 50)
    ]
    identifiers = [item["id"] for item in experiments]
    if len(set(identifiers)) != len(identifiers):
        raise ProjectError("experiment IDs must be unique within a plan")
    return {
        "schema_version": 1,
        "brief": {
            **{
                key: _text(brief.get(key, ""), f"brief.{key}")
                for key in ("question", "background", "success_criteria")
            },
            **{
                key: _texts(brief.get(key, []), f"brief.{key}")
                for key in ("constraints", "unknowns")
            },
        },
        "plan": {
            "summary": _text(plan.get("summary", ""), "plan.summary"),
            "experiments": experiments,
        },
        "claims": [_claim(item) for item in _list(obj.get("claims", []), "claims")],
        "next_step": _text(obj.get("next_step", ""), "next_step"),
    }


@dataclass(frozen=True, slots=True)
class ResearchDraft:
    """Canonical immutable JSON, with free Markdown for research prose."""

    content_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.content_json, str) or len(self.content_json.encode()) > 256 * 1024:
            raise ProjectError("research draft must be JSON of at most 256 KiB")
        try:
            document = _normalize(json.loads(self.content_json, object_pairs_hook=_unique_keys))
            normalized = json.dumps(
                document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError, RecursionError) as error:
            raise ProjectError(f"invalid research draft: {error}") from error
        if len(normalized.encode()) > 256 * 1024:
            raise ProjectError("normalized research draft exceeds 256 KiB")
        object.__setattr__(self, "content_json", normalized)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ResearchDraft:
        try:
            return cls(json.dumps(value, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError, RecursionError) as error:
            raise ProjectError(f"invalid research draft: {error}") from error

    def to_dict(self) -> dict[str, Any]:
        return dict(json.loads(self.content_json))

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.content_json.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchRevision:
    project_id: str
    revision: int
    draft: ResearchDraft
    reason: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "revision": self.revision,
            "digest": self.draft.digest,
            "document": self.draft.to_dict(),
            "reason": self.reason,
            "created_at": self.created_at,
        }
