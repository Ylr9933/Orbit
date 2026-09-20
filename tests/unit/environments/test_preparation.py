"""Intent policy, exact locks, and caller-supplied input rejection."""

import time

import pytest

from agent_infra.environments.preparation_api import EnvironmentIntent, EnvironmentProposal
from agent_infra.environments.preparation_locks import resolve_environment_lock
from agent_infra.environments.preparation_store import EnvironmentCatalog


@pytest.mark.parametrize(
    "patch",
    [
        {"dockerfile": "FROM anything"},
        {"network": "yes"},
        {"cpu": True},
        {"memory_bytes": 1},
        {"max_attempts": 0},
        {"attempt_seconds": float("inf")},
        {"base_image": "https://user:password@host"},
        {"imports": ["os;exit()"]},
        {"allowed_packages": ["--index-url=x"]},
        {"agent": "arbitrary"},
    ],
)
def test_intent_rejects_execution_and_budget_expansion(patch):
    with pytest.raises(ValueError):
        EnvironmentIntent.from_dict(
            {"goal": "CPU experiment", "base_image": "python:3.12-slim"} | patch
        )


@pytest.mark.parametrize(
    "dependencies",
    [
        ["numpy"],
        ["numpy @ https://secret@host/x.whl"],
        ["--extra-index-url=host"],
        ["../package"],
        ["torch==2.5.0"],
        ["six==1.16.0", "Six==1.17.0"],
    ],
)
def test_proposal_rejects_unpinned_paths_sources_and_disallowed_packages(dependencies):
    intent = EnvironmentIntent.from_dict(
        {"goal": "CPU", "base_image": "python", "network": True, "allowed_packages": ["six"]}
    )
    with pytest.raises(ValueError):
        EnvironmentProposal.from_dict(
            {"dependencies": dependencies, "source": "agent", "reason": "test"}, intent
        )


def test_repair_cannot_change_smoke_or_network():
    intent = EnvironmentIntent.from_dict(
        {"goal": "CPU", "base_image": "python", "imports": ["six"], "allowed_packages": ["six"]}
    )
    for extra in ({"imports": []}, {"network": True}, {"mounts": ["/home"]}):
        with pytest.raises(ValueError):
            EnvironmentProposal.from_dict(
                {"dependencies": [], "source": "agent", "reason": "test"} | extra, intent
            )
    with pytest.raises(ValueError, match="network"):
        EnvironmentProposal.from_dict(
            {"dependencies": ["six==1.17.0"], "source": "agent", "reason": "test"}, intent
        )


def test_catalog_close_and_lock_fail_closed(tmp_path):
    catalog = EnvironmentCatalog(tmp_path)
    plan = {
        "plan_id": "p",
        "project_id": "project",
        "proposals": [{}],
        "attempts": [{"attempt_id": "a", "status": "failed", "lock": None}],
    }
    catalog.save(plan)
    assert EnvironmentCatalog(tmp_path).get("project", "p") == plan
    with pytest.raises(KeyError):
        catalog.get("other", "p")
    with pytest.raises(ValueError, match="no successful"):
        resolve_environment_lock(catalog, "project", "p:a", lambda image: image)
    plan["attempts"][0].update(
        status="ready",
        cleanup_complete=True,
        lock={"proposal_revision": 1, "expires_at": time.time() - 1},
    )
    catalog.save(plan)
    with pytest.raises(ValueError, match="expired"):
        resolve_environment_lock(catalog, "project", "p:a", lambda image: image)
