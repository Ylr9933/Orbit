"""Public, no-service conformance helper for independent adapter package tests."""

from pathlib import Path

from agent_infra.benchmarks.api import (
    AdapterIdentity,
    BenchmarkAdapter,
    ExecutionPlan,
    PlanRequest,
)
from agent_infra.benchmarks.planning import freeze_plan
from agent_infra.benchmarks.registry import LoadedAdapter


def assert_planning_conformance(
    adapter: BenchmarkAdapter, source: Path, request: PlanRequest
) -> ExecutionPlan:
    """Check schema, catalog fidelity, source stability, validation and determinism.

    Does not attest the distribution, protocol equivalence, resources or runtime.
    Calls trusted adapter code twice; use only small fixtures in package tests.
    """
    identity = AdapterIdentity(
        distribution="conformance-test-only",
        version="0",
        entry_point="conformance-test-only",
        adapter_id=adapter.descriptor.adapter_id,
        sdk_version=adapter.descriptor.sdk_version,
    )
    loaded = LoadedAdapter(adapter, identity)
    first = freeze_plan(loaded, source, request)
    second = freeze_plan(loaded, source, request)
    if first != second:
        raise ValueError("adapter discovery/planning is not deterministic for the same inputs")
    return first.plan
