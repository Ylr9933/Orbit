"""Resolve an exact, fresh environment validation; never trust an exported lock alone."""

import time
from collections.abc import Callable
from typing import Any

from agent_infra.environments.preparation_api import SMOKE_VERSION, TEMPLATE_VERSION, digest
from agent_infra.environments.preparation_store import EnvironmentCatalog


def resolve_environment_lock(
    catalog: EnvironmentCatalog,
    project: str,
    lock_id: str,
    image: Callable[[str], str],
    *,
    agent: str | None = None,
) -> dict[str, Any]:
    try:
        plan_id, attempt_id = lock_id.split(":")
    except (ValueError, AttributeError) as error:
        raise ValueError("environment lock must be plan_id:attempt_id") from error
    plan = catalog.get(project, plan_id)
    attempt = next((a for a in plan["attempts"] if a["attempt_id"] == attempt_id), None)
    if attempt is None:
        raise ValueError("environment attempt not found")
    lock = attempt.get("lock")
    if not lock or attempt["status"] != "ready" or not attempt.get("cleanup_complete"):
        raise ValueError("environment has no successful, cleaned validation")
    if lock["proposal_revision"] != len(plan["proposals"]):
        raise ValueError("environment proposal changed; validate the current revision")
    if lock["expires_at"] <= time.time():
        raise ValueError("environment validation expired; prepare again to revalidate")
    if lock["template_version"] != TEMPLATE_VERSION or lock["smoke_version"] != SMOKE_VERSION:
        raise ValueError("environment validator changed; prepare again")
    if lock["intent_digest"] != digest(plan["intent"]):
        raise ValueError("environment intent changed")
    proposal = plan["proposals"][lock["proposal_revision"] - 1]
    if lock["proposal_digest"] != digest(
        {key: proposal[key] for key in ("dependencies", "source", "reason")}
    ):
        raise ValueError("environment proposal content changed")
    if agent is not None and lock["agent"] != agent:
        raise ValueError("environment lock does not validate the requested agent layer")
    if image(lock["image_id"]) != lock["image_id"]:
        raise ValueError("locked image is unavailable")
    return dict(lock)
