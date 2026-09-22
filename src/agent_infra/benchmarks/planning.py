"""Validated, content-addressed planning; no scheduling or runtime side effects."""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

from agent_infra.benchmarks.api import (
    SDK_VERSION,
    AdapterIdentity,
    CapabilityProfile,
    Catalog,
    CompatibilityClaim,
    Contract,
    Digest,
    ExecutionPlan,
    Issue,
    PlanRequest,
)
from agent_infra.benchmarks.registry import AdapterError, LoadedAdapter
from agent_infra.contracts.files import content_digest


def canonical_digest(value: object) -> str:
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


class SourceSnapshot(Contract):
    path: str
    digest: Digest


class PlanBody(Contract):
    schema_version: int = 1
    sdk_version: str = SDK_VERSION
    adapter: AdapterIdentity
    source: SourceSnapshot
    catalog_digest: Digest
    plan: ExecutionPlan


class FrozenPlan(PlanBody):
    digest: Digest


def adapter_call[T: Contract](operation: str, callback: Callable[[], T], expected: type[T]) -> T:
    try:
        result = callback()
        if not isinstance(result, expected):
            raise AdapterError(f"adapter {operation} must return SDK {expected.__name__}")
        # Revalidate even objects constructed with model_construct or model_copy(update=...).
        return expected.model_validate_json(result.model_dump_json(warnings="error"))
    except AdapterError:
        raise
    except Exception as error:
        raise AdapterError(f"adapter {operation} failed: {type(error).__name__}") from error


def discover(loaded: LoadedAdapter, source: Path) -> tuple[Catalog, SourceSnapshot]:
    # Reject symlinks before resolve, including parent components.
    absolute = source.absolute()
    if any(path.is_symlink() for path in (absolute, *absolute.parents)):
        raise AdapterError("source path must not contain symlinks")
    before = content_digest(absolute)
    catalog = adapter_call("discover", lambda: loaded.implementation.discover(absolute), Catalog)
    if content_digest(absolute) != before:
        raise AdapterError("source changed during discovery; retry with an immutable snapshot")
    return catalog, SourceSnapshot(path=str(absolute), digest=before)


def adapter_issues(loaded: LoadedAdapter, plan: ExecutionPlan) -> tuple[Issue, ...]:
    try:
        issues = loaded.implementation.validate(plan)
        if not isinstance(issues, tuple) or not all(isinstance(issue, Issue) for issue in issues):
            raise AdapterError("adapter validate must return a tuple of SDK Issue objects")
        return tuple(Issue.model_validate_json(item.model_dump_json()) for item in issues)
    except AdapterError:
        raise
    except Exception as error:
        raise AdapterError(f"adapter validate failed: {type(error).__name__}") from error


def freeze_plan(loaded: LoadedAdapter, source: Path, request: PlanRequest) -> FrozenPlan:
    catalog, snapshot = discover(loaded, source)
    by_id = {unit.unit_id: unit for unit in catalog.units}
    if set(request.selection) - set(by_id):
        raise AdapterError("selection contains units absent from this catalog")
    plan = adapter_call("plan", lambda: loaded.implementation.plan(catalog, request), ExecutionPlan)
    if plan.request != request or plan.suite != catalog.suite:
        raise AdapterError(
            "adapter changed the requested candidate, parameters, selection or suite"
        )
    if plan.units != tuple(by_id[key] for key in request.selection):
        raise AdapterError(
            "adapter changed catalog units, episode order or condition/state policies"
        )
    errors = [
        f"{issue.code}: {issue.message}"
        for issue in adapter_issues(loaded, plan)
        if issue.severity == "error"
    ]
    if errors:
        raise AdapterError("adapter rejected plan: " + ", ".join(errors))
    if content_digest(Path(snapshot.path)) != snapshot.digest:
        raise AdapterError("source changed during planning")
    body = PlanBody(
        adapter=loaded.identity,
        source=snapshot,
        catalog_digest=canonical_digest(catalog.model_dump(mode="json")),
        plan=plan,
    )
    return FrozenPlan(**body.model_dump(), digest=canonical_digest(body.model_dump(mode="json")))


def write_plan(plan: FrozenPlan, output: Path) -> None:
    # Never overwrite an existing plan, source or config. Plans are administrator documents.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(plan.model_dump_json(indent=2) + "\n")


def read_plan(path: Path) -> FrozenPlan:
    plan = FrozenPlan.model_validate_json(path.read_bytes())
    if plan.schema_version != 1 or plan.sdk_version != SDK_VERSION:
        raise AdapterError("unsupported frozen plan schema or SDK version")
    body = plan.model_dump(mode="json", exclude={"digest"})
    if canonical_digest(body) != plan.digest:
        raise AdapterError("frozen plan digest mismatch; regenerate the plan")
    return plan


def check_plan(
    frozen: FrozenPlan, loaded: LoadedAdapter, profile: CapabilityProfile
) -> tuple[Issue, ...]:
    catalog, snapshot = discover(loaded, Path(frozen.source.path))
    issues: list[Issue] = []
    if (
        snapshot != frozen.source
        or canonical_digest(catalog.model_dump(mode="json")) != frozen.catalog_digest
    ):
        issues.append(Issue(code="source_changed", message="Source or catalog changed; plan again"))
    # Detect changed adapter/config behavior at the same declared version.
    current = freeze_plan(loaded, Path(frozen.source.path), frozen.plan.request)
    if current.digest != frozen.digest:
        issues.append(
            Issue(code="plan_changed", message="Adapter produced a different plan; review")
        )
    issues.extend(adapter_issues(loaded, frozen.plan))
    if frozen.plan.request.candidate.agent not in profile.agents:
        issues.append(
            Issue(code="agent_unavailable", message="Agent is absent from capability profile")
        )
    backends = {item.backend: item for item in profile.backends}
    for phase in frozen.plan.phases:
        candidate = frozen.plan.request.candidate
        expected = CompatibilityClaim(
            adapter_id=frozen.adapter.adapter_id,
            adapter_version=frozen.adapter.version,
            suite_digest=frozen.plan.suite.source.digest,
            runner_digest=frozen.plan.suite.runner.digest,
            profile=frozen.plan.suite.profile,
            agent=candidate.agent,
            agent_version=candidate.agent_version,
            model=candidate.model,
            backend=phase.backend,
        )
        if expected not in profile.combinations:
            issues.append(
                Issue(
                    code="combination_unverified",
                    message=f"{phase.phase_id}: exact Agent/backend/protocol tuple is undeclared",
                )
            )
        backend = backends.get(phase.backend)
        if backend is None:
            issues.append(
                Issue(code="backend_unavailable", message=f"Missing backend: {phase.backend}")
            )
        else:
            for feature in sorted(set(phase.required_capabilities) - set(backend.features)):
                issues.append(
                    Issue(
                        code="capability_missing",
                        message=f"{phase.phase_id}: {phase.backend} requires {feature}",
                    )
                )
    return tuple(issues)
