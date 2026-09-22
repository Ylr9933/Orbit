"""An independent execution-extension example; no Agent, Docker or benchmark scorer."""

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from agent_infra.benchmarks.api import (
    AdapterDescriptor,
    Budget,
    Catalog,
    ExecutionPlan,
    Issue,
    Phase,
    PinnedSource,
    PlanRequest,
    RetryPolicy,
    SuiteRef,
    WorkUnit,
)
from agent_infra.benchmarks.execution_api import NativeInvocation
from agent_infra.environments.api import ProcessCommand

RUNNER = (
    "import json,sys,time; from pathlib import Path; time.sleep(1.0); "
    "result={'sum': sum(json.loads(sys.argv[1])['numbers'])}; "
    "Path('result.json').write_text(json.dumps(result)); print(json.dumps(result), flush=True)"
)


class Adapter:
    descriptor = AdapterDescriptor(adapter_id="process-demo", description="Cooperative CPU fixture")

    def discover(self, source: Path) -> Catalog:
        path = source / "input.json"
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        return Catalog(
            suite=SuiteRef(
                benchmark="synthetic-process",
                profile="sum-v1",
                synthetic=True,
                source=PinnedSource(
                    uri=path.as_uri(), revision=checksum, digest="sha256:" + checksum
                ),
                runner=PinnedSource(
                    uri="urn:process-demo:runner",
                    revision="1",
                    digest="sha256:" + hashlib.sha256(RUNNER.encode()).hexdigest(),
                ),
            ),
            units=(WorkUnit(unit_id="sum", native_id="sum", kind="native_job"),),
        )

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        return ExecutionPlan(
            suite=catalog.suite,
            request=request,
            units=catalog.units,
            phases=(
                Phase(
                    phase_id="native",
                    kind="native",
                    owner="native",
                    backend="managed-process-v1",
                    required_capabilities=(
                        "durable_operation",
                        "bounded_logs",
                        "process_group_cleanup",
                        "wall_timeout",
                    ),
                    budget=Budget(wall_seconds=30, clock="process_start"),
                ),
            ),
            retry=RetryPolicy(owner="none", max_attempts=1),
        )

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        if plan.request.parameters:
            return (Issue(code="unsupported_parameter", message="The fixture accepts no options"),)
        return ()

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation:
        path = Path(unquote(urlparse(plan.suite.source.uri).path))
        data = json.loads(path.read_bytes())
        return NativeInvocation(
            command=ProcessCommand(
                (sys.executable, "-c", RUNNER, json.dumps(data)), cwd=".", timeout_seconds=30
            ),
            outputs=("result.json",),
        )
