"""Backend-neutral records, trace, artifact, and trajectory contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol


class ProducerKind(StrEnum):
    RUN = "run"
    AGENT = "agent"
    ENVIRONMENT = "environment"
    RESOURCE = "resource"
    EVALUATOR = "evaluator"
    USER = "user"
    RECORDS = "records"


class Visibility(StrEnum):
    AGENT = "agent"
    USER = "user"
    CONTROLLER = "controller"
    EVALUATOR = "evaluator"
    ADMIN = "admin"


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    USER_PRIVATE = "user_private"
    PRIVATE_EVALUATION = "private_evaluation"
    CREDENTIAL = "credential"
    SECRET = "secret"


class CaptureStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    TRUNCATED = "truncated"
    REDACTED = "redacted"
    UNAVAILABLE = "unavailable"


class DurabilityLevel(StrEnum):
    ACCEPTED = "accepted"
    DURABLE_LOCAL = "durable_local"
    DURABLE_PRIMARY = "durable_primary"
    ARCHIVED = "archived"


class RecordingMode(StrEnum):
    REQUIRED = "required"
    BEST_EFFORT = "best_effort"


@dataclass(frozen=True, slots=True)
class RecordingPolicy:
    mode: RecordingMode = RecordingMode.REQUIRED
    durability_before_cleanup: DurabilityLevel = DurabilityLevel.DURABLE_LOCAL
    capture_agent_native: bool = True
    capture_stdout_stderr: bool = True
    capture_resource_samples: bool = True
    stream_bytes_per_job: int = 8 * 1024**2
    total_bytes_per_attempt: int = 1024**3

    def __post_init__(self) -> None:
        if self.stream_bytes_per_job <= 0 or self.total_bytes_per_attempt <= 0:
            raise ValueError("recording limits must be positive")


@dataclass(frozen=True, slots=True)
class RecordContext:
    run_id: str
    attempt_id: str
    producer_id: str
    producer_kind: ProducerKind
    phase_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("run_id", "attempt_id", "producer_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class EventLink:
    relation: str
    span_id: str | None = None
    event_id: str | None = None

    def __post_init__(self) -> None:
        if not self.relation.strip() or (self.span_id is None and self.event_id is None):
            raise ValueError("event links require a relation and a target")


@dataclass(frozen=True, slots=True)
class EventDraft:
    event_type: str
    payload: Mapping[str, object] = field(default_factory=dict)
    payload_schema: str = "records.payload.v1"
    producer_sequence: int | None = None
    idempotency_key: str | None = None
    observed_at: datetime | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    links: tuple[EventLink, ...] = ()
    correlation: Mapping[str, str] = field(default_factory=dict)
    raw_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    visibility: Visibility = Visibility.CONTROLLER
    data_class: DataClass = DataClass.INTERNAL
    capture_status: CaptureStatus = CaptureStatus.COMPLETE
    normalizer_name: str | None = None
    normalizer_version: str | None = None

    def __post_init__(self) -> None:
        if not self.event_type.strip() or not self.payload_schema.strip():
            raise ValueError("event type and payload schema must not be empty")
        if self.producer_sequence is not None and self.producer_sequence < 0:
            raise ValueError("producer_sequence must be non-negative")
        if self.idempotency_key is not None and not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must include a timezone")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    schema_version: str
    event_id: str
    event_index: int
    event_type: str
    context: RecordContext
    producer_sequence: int
    observed_at: datetime
    ingested_at: datetime
    payload_schema: str
    payload: Mapping[str, object]
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    links: tuple[EventLink, ...] = ()
    correlation: Mapping[str, str] = field(default_factory=dict)
    raw_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    visibility: Visibility = Visibility.CONTROLLER
    data_class: DataClass = DataClass.INTERNAL
    capture_status: CaptureStatus = CaptureStatus.COMPLETE
    normalizer_name: str | None = None
    normalizer_version: str | None = None
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class BlobRef:
    digest: str
    size_bytes: int
    media_type: str


@dataclass(frozen=True, slots=True)
class StreamRef:
    stream_id: str
    name: str
    blob: BlobRef | None
    size_bytes: int
    capture_status: CaptureStatus


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    name: str
    kind: str
    digest: str
    size_bytes: int
    media_type: str
    manifest_blob: BlobRef
    visibility: Visibility
    data_class: DataClass


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    durability: DurabilityLevel
    accepted: int
    identifiers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    created_at: datetime
    request: Mapping[str, object]
    recording_policy: RecordingPolicy = RecordingPolicy()


@dataclass(frozen=True, slots=True)
class AttemptManifest:
    attempt_id: str
    run_id: str
    started_at: datetime
    task_id: str | None = None
    task_digest: str | None = None
    policy_snapshot: Mapping[str, object] = field(default_factory=dict)
    environment_snapshot: Mapping[str, object] = field(default_factory=dict)
    coverage: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunRecord:
    manifest: RunManifest
    status: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    manifest: AttemptManifest
    status: str
    finished_at: datetime | None
    result: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class EventQuery:
    run_id: str | None = None
    attempt_id: str | None = None
    event_types: tuple[str, ...] = ()
    producer_kinds: tuple[ProducerKind, ...] = ()
    limit: int = 200

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 10_000:
            raise ValueError("event query limit must be between 1 and 10000")


@dataclass(frozen=True, slots=True)
class EventPage:
    items: tuple[EventEnvelope, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TraceSpan:
    span_id: str
    parent_span_id: str | None
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TraceGraph:
    attempt_id: str
    events: tuple[EventEnvelope, ...]
    spans: tuple[TraceSpan, ...]


class RecordSink(Protocol):
    @property
    def context(self) -> RecordContext: ...

    def append_events(self, events: Sequence[EventDraft]) -> WriteReceipt: ...

    def put_blob(self, data: bytes, *, media_type: str) -> BlobRef: ...

    def start_stream(
        self,
        stream_id: str,
        name: str,
        *,
        media_type: str = "application/octet-stream",
        visibility: Visibility = Visibility.CONTROLLER,
        data_class: DataClass = DataClass.INTERNAL,
    ) -> None: ...

    def append_stream(self, stream_id: str, chunk: bytes, offset: int) -> WriteReceipt: ...

    def finalize_stream(
        self, stream_id: str, status: CaptureStatus = CaptureStatus.COMPLETE
    ) -> StreamRef: ...

    def commit_artifact(
        self,
        path: Path,
        *,
        name: str,
        media_type: str = "application/octet-stream",
        visibility: Visibility = Visibility.USER,
        data_class: DataClass = DataClass.USER_PRIVATE,
    ) -> ArtifactRef: ...


class RecordsWriter(Protocol):
    def begin_run(self, manifest: RunManifest) -> RunRecord: ...

    def begin_attempt(self, manifest: AttemptManifest) -> AttemptRecord: ...

    def scoped_sink(self, context: RecordContext) -> RecordSink: ...

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        result: Mapping[str, object],
    ) -> WriteReceipt: ...

    def finish_run(self, run_id: str, *, status: str) -> WriteReceipt: ...


class RecordsReader(Protocol):
    def get_run(self, run_id: str) -> RunRecord: ...

    def get_attempt(self, attempt_id: str) -> AttemptRecord: ...

    def list_attempts(self, run_id: str) -> tuple[AttemptRecord, ...]: ...

    def read_events(self, query: EventQuery, cursor: str | None = None) -> EventPage: ...

    def read_trace(self, attempt_id: str) -> TraceGraph: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRef: ...

    def list_artifacts(self, attempt_id: str) -> tuple[ArtifactRef, ...]: ...

    def open_blob(self, ref: BlobRef) -> BinaryIO: ...
