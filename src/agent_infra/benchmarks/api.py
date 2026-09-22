"""Public SDK 1.0. Planning is side-effect-free; execution belongs to Run/backends.

Import contracts from this module, not package internals. Models are immutable JSON
values. Unknown fields fail rather than silently changing a benchmark's semantics.
"""

from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SDK_VERSION = "1.0"
ENTRY_POINT_GROUP = "agent_infra.benchmarks.v1"
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S(?:.*\S)?$")]
PositiveInt = Annotated[int, Field(gt=0)]
Role = Literal["solver", "training", "public_eval", "grader", "optimizer", "admin"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False, hide_input_in_errors=True
    )

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def strict_schema_version(cls, data: Any) -> Any:
        if type(data) is not int:
            raise ValueError("schema_version must be an integer")
        return data


class PinnedSource(Contract):
    uri: Name
    revision: Name
    digest: Digest

    @model_validator(mode="after")
    def pinned(self) -> Self:
        if self.revision.lower() in {"main", "master", "head", "latest"}:
            raise ValueError("source revision must be immutable, not a moving alias")
        return self


class SuiteRef(Contract):
    benchmark: Name
    source: PinnedSource
    runner: PinnedSource
    dataset: PinnedSource | None = None
    profile: Name
    synthetic: bool = False


class CandidateRef(Contract):
    candidate_id: Name
    agent: Name
    agent_version: Name
    model: Name
    configuration_digest: Digest
    target_model: PinnedSource | None = None
    judge: PinnedSource | None = None


class StatePolicy(Contract):
    session: Literal["fresh", "resume", "native", "unspecified"]
    workspace: Literal["reset", "preserve", "native", "unspecified"]
    conversation: Literal["discard", "preserve", "native", "unspecified"]
    memory: Literal["none", "native_scoped", "snapshot", "unspecified"]
    checkpoint: Literal["none", "native_scoped", "snapshot", "unspecified"]
    scope: Literal["episode", "sequence", "condition", "trial", "unspecified"]
    owner: Name
    native_policy: PinnedSource | None = None


class Condition(Contract):
    condition_id: Name
    state: StatePolicy


class WorkUnit(Contract):
    unit_id: Name
    native_id: Name
    kind: Literal["single", "sequence", "paired_sequence", "native_job"]
    episodes: tuple[Name, ...] = ()
    conditions: tuple[Condition, ...] = ()

    @model_validator(mode="after")
    def atomic_unit(self) -> Self:
        if len(set(self.episodes)) != len(self.episodes):
            raise ValueError("episode IDs must be unique and ordered within a unit")
        conditions = [item.condition_id for item in self.conditions]
        if len(set(conditions)) != len(conditions):
            raise ValueError("condition IDs must be unique")
        if self.kind in {"sequence", "paired_sequence"} and not self.episodes:
            raise ValueError("a sequence requires its ordered episode IDs")
        if self.kind == "paired_sequence" and len(self.conditions) < 2:
            raise ValueError("paired sequences require at least two explicit conditions")
        return self


class Catalog(Contract):
    suite: SuiteRef
    units: tuple[WorkUnit, ...]

    @model_validator(mode="after")
    def unique_units(self) -> Self:
        identifiers = [unit.unit_id for unit in self.units]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("catalog unit IDs must be unique")
        return self


class Parameter(Contract):
    key: Name
    value: str


class PlanRequest(Contract):
    selection: Annotated[tuple[Name, ...], Field(min_length=1)]
    candidate: CandidateRef
    parameters: tuple[Parameter, ...] = ()

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        if len(set(self.selection)) != len(self.selection):
            raise ValueError("selection must not contain duplicate units")
        keys = [item.key for item in self.parameters]
        if len(set(keys)) != len(keys):
            raise ValueError("parameter keys must be unique")
        return self


class ResourceRequirements(Contract):
    """Native requirements, NOT an allocation. None means unspecified, not zero.

    Run must resolve these into the existing resources.api.ResourceRequest before
    local admission. External allocators keep their own allocation authority.
    """

    cpu_cores: Annotated[float, Field(gt=0)] | None = None
    memory_bytes: PositiveInt | None = None
    gpu_count: Annotated[int, Field(ge=0)] | None = None
    gpu_model: Name | None = None
    gpu_memory_bytes: PositiveInt | None = None
    disk_bytes: PositiveInt | None = None
    allocator: Literal["local", "external", "unspecified"] = "unspecified"


class Budget(Contract):
    wall_seconds: PositiveInt | None = None
    clock: Name | None = None

    @model_validator(mode="after")
    def clock_required(self) -> Self:
        if (self.wall_seconds is None) != (self.clock is None):
            raise ValueError("a time budget requires both duration and native clock definition")
        return self


class Material(Contract):
    material_id: Name
    source: PinnedSource
    purpose: Name
    readers: Annotated[tuple[Role, ...], Field(min_length=1)]


class Phase(Contract):
    phase_id: Name
    kind: Literal["solve", "train", "evaluate", "judge", "collect", "submit", "native"]
    owner: Literal["native", "platform"]
    backend: Name
    depends_on: tuple[Name, ...] = ()
    required_capabilities: tuple[Name, ...] = ()
    resources: ResourceRequirements = ResourceRequirements()
    budget: Budget = Budget()
    materials: tuple[Material, ...] = ()
    native_config: PinnedSource | None = None


class FeedbackRule(Contract):
    recipient: Role
    fields: tuple[Name, ...]
    release: Literal["during_trial", "after_trial", "after_campaign", "never"]
    purpose: Name
    max_queries: PositiveInt | None = None


class RetryPolicy(Contract):
    owner: Literal["native", "platform", "none", "unspecified"]
    max_attempts: PositiveInt | None = None
    before_solver_only: bool | None = None
    native_rule: PinnedSource | None = None


class ExecutionPlan(Contract):
    schema_version: Literal[1] = 1
    suite: SuiteRef
    request: PlanRequest
    units: Annotated[tuple[WorkUnit, ...], Field(min_length=1)]
    phases: Annotated[tuple[Phase, ...], Field(min_length=1)]
    retry: RetryPolicy
    feedback: tuple[FeedbackRule, ...] = ()
    limitations: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def references(self) -> Self:
        if tuple(unit.unit_id for unit in self.units) != self.request.selection:
            raise ValueError("plan units must exactly preserve requested selection and order")
        seen: set[str] = set()
        for phase in self.phases:
            if phase.phase_id in seen:
                raise ValueError("phase IDs must be unique")
            if set(phase.depends_on) - seen:
                raise ValueError(
                    "phases must be topologically ordered, without missing dependencies"
                )
            seen.add(phase.phase_id)
            materials = [item.material_id for item in phase.materials]
            if len(set(materials)) != len(materials):
                raise ValueError("material IDs must be unique within a phase")
        return self


class AdapterDescriptor(Contract):
    adapter_id: Name
    sdk_version: Name = SDK_VERSION
    description: Name


class AdapterIdentity(Contract):
    distribution: Name
    version: Name
    entry_point: Name
    adapter_id: Name
    sdk_version: Name


class Issue(Contract):
    code: Name
    message: Name
    severity: Literal["error", "warning"] = "error"


class BackendCapabilities(Contract):
    backend: Name
    features: tuple[Name, ...] = ()


class CompatibilityClaim(Contract):
    """Exact version tuple claimed by an operator, not inferred from a CLI being installed."""

    adapter_id: Name
    adapter_version: Name
    suite_digest: Digest
    runner_digest: Digest
    profile: Name
    agent: Name
    agent_version: Name
    model: Name
    backend: Name


class CapabilityProfile(Contract):
    """Operator declarations for offline comparison; never runtime attestation."""

    schema_version: Literal[1] = 1
    backends: tuple[BackendCapabilities, ...] = ()
    agents: tuple[Name, ...] = ()
    combinations: tuple[CompatibilityClaim, ...] = ()

    @model_validator(mode="after")
    def unique_backends(self) -> Self:
        names = [item.backend for item in self.backends]
        if len(set(names)) != len(names):
            raise ValueError("capability profile backend IDs must be unique")
        return self


class Metric(Contract):
    name: Name
    value: float
    direction: Literal["maximize", "minimize", "none"]
    unit: Name
    scope: Name
    evidence_artifact_id: Name


class BenchmarkOutcome(Contract):
    """References existing Run/Attempt/Records IDs; does not create another event store."""

    run_id: Name
    attempt_id: Name
    unit_id: Name
    execution: Literal["completed", "failed", "cancelled", "unknown"]
    evaluation: Literal["scored", "failed", "pending", "not_applicable", "unknown"]
    protocol: Literal["valid", "invalid", "review_required", "unknown"]
    cleanup: Literal["confirmed", "pending", "failed", "unknown"]
    capture: Literal["complete", "partial", "missing", "unknown"]
    submission: Literal["not_requested", "pending", "accepted", "rejected", "unknown"]
    metrics: tuple[Metric, ...] = ()
    evidence_artifact_ids: tuple[Name, ...] = ()
    native_rule: PinnedSource | None = None


class BenchmarkAdapter(Protocol):
    """BM00 planning surface. Never launch jobs, download, install or call models here.

    Execution/evidence interpretation will be separately versioned extensions;
    no fake submit/score methods are required of planning-only packages.
    """

    @property
    def descriptor(self) -> AdapterDescriptor: ...

    def discover(self, source: Path) -> Catalog: ...

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan: ...

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]: ...
