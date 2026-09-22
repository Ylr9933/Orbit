"""Independent SDK consumer with synthetic fixtures, not native benchmark support."""

import hashlib
from pathlib import Path

from agent_infra.benchmarks.api import (
    AdapterDescriptor,
    Catalog,
    Contract,
    ExecutionPlan,
    FeedbackRule,
    Issue,
    Phase,
    PinnedSource,
    PlanRequest,
    RetryPolicy,
    SuiteRef,
    WorkUnit,
)


class Fixture(Contract):
    benchmark: str
    profile: str
    units: tuple[WorkUnit, ...]
    phases: tuple[Phase, ...]
    retry: RetryPolicy
    feedback: tuple[FeedbackRule, ...]


class Adapter:
    descriptor = AdapterDescriptor(
        adapter_id="contract-demo",
        description="Four synthetic protocol shapes; planning only, no native benchmark code",
    )

    def discover(self, source: Path) -> Catalog:
        payload = (source / "protocol.json").read_bytes()
        fixture = Fixture.model_validate_json(payload)
        checksum = hashlib.sha256(payload).hexdigest()
        pinned = PinnedSource(
            uri=(source / "protocol.json").as_uri(),
            revision=checksum,
            digest="sha256:" + checksum,
        )
        return Catalog(
            suite=SuiteRef(
                benchmark=fixture.benchmark,
                source=pinned,
                runner=PinnedSource(
                    uri="urn:agent-infra:synthetic-runner",
                    revision="fixture-v1",
                    digest="sha256:" + hashlib.sha256(b"synthetic-runner-v1").hexdigest(),
                ),
                profile=fixture.profile,
                synthetic=True,
            ),
            units=fixture.units,
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        # Read a pinned local manifest; never install dependencies or launch a job here.
        from urllib.parse import unquote, urlparse

        source = Path(unquote(urlparse(catalog.suite.source.uri).path))
        fixture = Fixture.model_validate_json(source.read_bytes())
        indexed = {unit.unit_id: unit for unit in catalog.units}
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=tuple(indexed[key] for key in request.selection),
            phases=fixture.phases,
            retry=fixture.retry,
            feedback=fixture.feedback,
            limitations=("Synthetic contract fixture; no execution or official equivalence",),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        if plan.request.parameters:
            return (Issue(code="unsupported_parameter", message="Demo accepts no native options"),)
        return ()
