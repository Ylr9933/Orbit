"""SQLite metadata and filesystem content-addressed storage for local execution."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, BinaryIO, cast

from agent_infra.contracts.files import content_digest
from agent_infra.records.api import (
    ArtifactRef,
    AttemptManifest,
    AttemptRecord,
    BlobRef,
    CaptureStatus,
    DataClass,
    DurabilityLevel,
    EventDraft,
    EventEnvelope,
    EventLink,
    EventPage,
    EventQuery,
    ProducerKind,
    RecordContext,
    RunManifest,
    RunRecord,
    StreamRef,
    TraceGraph,
    TraceSpan,
    Visibility,
    WriteReceipt,
)

_SCHEMA_VERSION = 1


def _now() -> datetime:
    return datetime.now(UTC)


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("record timestamps must include a timezone")
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"record value is not JSON-compatible: {type(value).__name__}")


def _dumps(value: object) -> str:
    return json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _mapping(value: str) -> dict[str, object]:
    result = json.loads(value)
    if not isinstance(result, dict):
        raise RuntimeError("stored record is not a JSON object")
    return cast(dict[str, object], result)


def _strings(value: str) -> tuple[str, ...]:
    result = json.loads(value)
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise RuntimeError("stored record is not a string list")
    return tuple(result)


class LocalRecordsStore:
    """Thread-safe local backend with one SQLite transaction per public mutation."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.blob_root = self.root / "blobs" / "sha256"
        self.spool_root = self.root / "spool"
        self.export_root = self.root / "exports"
        for directory in (self.blob_root, self.spool_root, self.export_root):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.root / "records.sqlite3"
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    result_json TEXT
                );
                CREATE INDEX IF NOT EXISTS attempts_run_idx ON attempts(run_id, started_at);
                CREATE TABLE IF NOT EXISTS producer_sequences (
                    producer_id TEXT PRIMARY KEY,
                    next_sequence INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_index INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    schema_version TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    phase_id TEXT,
                    session_id TEXT,
                    producer_id TEXT NOT NULL,
                    producer_kind TEXT NOT NULL,
                    producer_sequence INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    payload_schema TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    trace_id TEXT,
                    span_id TEXT,
                    parent_span_id TEXT,
                    links_json TEXT NOT NULL,
                    correlation_json TEXT NOT NULL,
                    raw_refs_json TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    capture_status TEXT NOT NULL,
                    normalizer_name TEXT,
                    normalizer_version TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    UNIQUE(producer_id, producer_sequence)
                );
                CREATE INDEX IF NOT EXISTS events_attempt_idx
                    ON events(attempt_id, event_index);
                CREATE INDEX IF NOT EXISTS events_type_idx
                    ON events(event_type, event_index);
                CREATE TABLE IF NOT EXISTS blobs (
                    digest TEXT PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS streams (
                    stream_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    producer_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    spool_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    capture_status TEXT NOT NULL,
                    blob_digest TEXT REFERENCES blobs(digest)
                );
                CREATE INDEX IF NOT EXISTS streams_attempt_idx ON streams(attempt_id);
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    producer_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL REFERENCES blobs(digest),
                    visibility TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_attempt_idx ON artifacts(attempt_id);
                """
            )
            row = connection.execute("SELECT version FROM schema_info").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_info(version) VALUES (?)", (_SCHEMA_VERSION,)
                )
            elif row["version"] != _SCHEMA_VERSION:
                raise RuntimeError(f"unsupported Records schema version: {row['version']}")
            connection.commit()
        self.database.chmod(0o600)

    def begin_run(self, manifest: RunManifest) -> RunRecord:
        if manifest.created_at.tzinfo is None or manifest.created_at.utcoffset() is None:
            raise ValueError("run created_at must include a timezone")
        encoded = _dumps(asdict(manifest))
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT manifest_json, status FROM runs WHERE run_id=?", (manifest.run_id,)
            ).fetchone()
            if row is not None:
                if row["manifest_json"] != encoded:
                    raise ValueError("run ID already has a different manifest")
                return RunRecord(manifest, str(row["status"]))
            connection.execute(
                "INSERT INTO runs(run_id,created_at,status,manifest_json) VALUES (?,?,?,?)",
                (manifest.run_id, manifest.created_at.isoformat(), "running", encoded),
            )
            connection.commit()
        return RunRecord(manifest, "running")

    def begin_attempt(self, manifest: AttemptManifest) -> AttemptRecord:
        if manifest.started_at.tzinfo is None or manifest.started_at.utcoffset() is None:
            raise ValueError("attempt started_at must include a timezone")
        encoded = _dumps(asdict(manifest))
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT manifest_json,status,finished_at,result_json
                   FROM attempts WHERE attempt_id=?""",
                (manifest.attempt_id,),
            ).fetchone()
            if row is not None:
                if row["manifest_json"] != encoded:
                    raise ValueError("attempt ID already has a different manifest")
                return AttemptRecord(
                    manifest,
                    str(row["status"]),
                    datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                    _mapping(row["result_json"]) if row["result_json"] else None,
                )
            connection.execute(
                """INSERT INTO attempts(
                       attempt_id,run_id,started_at,status,manifest_json
                   ) VALUES (?,?,?,?,?)""",
                (
                    manifest.attempt_id,
                    manifest.run_id,
                    manifest.started_at.isoformat(),
                    "running",
                    encoded,
                ),
            )
            connection.commit()
        return AttemptRecord(manifest, "running", None, None)

    def scoped_sink(self, context: RecordContext) -> _LocalRecordSink:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM attempts WHERE attempt_id=? AND run_id=?",
                (context.attempt_id, context.run_id),
            ).fetchone()
        if row is None:
            raise KeyError("record context refers to an unknown run attempt")
        return _LocalRecordSink(self, context)

    def finish_attempt(
        self, attempt_id: str, *, status: str, result: Mapping[str, object]
    ) -> WriteReceipt:
        if not status.strip():
            raise ValueError("attempt status must not be empty")
        finished_at = _now().isoformat()
        encoded = _dumps(result)
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                """UPDATE attempts SET status=?,finished_at=?,result_json=?
                   WHERE attempt_id=? AND status='running'""",
                (status, finished_at, encoded, attempt_id),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT status,result_json FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(attempt_id)
                if row["status"] != status or row["result_json"] != encoded:
                    raise ValueError("attempt is already finished with another result")
            connection.commit()
        return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, 1, (attempt_id,))

    def finish_run(self, run_id: str, *, status: str) -> WriteReceipt:
        if not status.strip():
            raise ValueError("run status must not be empty")
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
            if cursor.rowcount != 1:
                raise KeyError(run_id)
            connection.commit()
        return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, 1, (run_id,))

    def list_runs(self, *, limit: int = 100, offset: int = 0) -> tuple[RunRecord, ...]:
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("invalid Run page")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC,run_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return tuple(
            RunRecord(self._decode_run_manifest(row["manifest_json"]), str(row["status"]))
            for row in rows
        )

    def get_run(self, run_id: str) -> RunRecord:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRecord(self._decode_run_manifest(row["manifest_json"]), str(row["status"]))

    def get_attempt(self, attempt_id: str) -> AttemptRecord:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        if row is None:
            raise KeyError(attempt_id)
        return self._decode_attempt(row)

    def list_attempts(self, run_id: str) -> tuple[AttemptRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM attempts WHERE run_id=? ORDER BY started_at,attempt_id", (run_id,)
            ).fetchall()
        return tuple(self._decode_attempt(row) for row in rows)

    def read_events(self, query: EventQuery, cursor: str | None = None) -> EventPage:
        after = 0
        if cursor is not None:
            try:
                after = int(cursor)
            except ValueError as error:
                raise ValueError("invalid event cursor") from error
            if after < 0:
                raise ValueError("invalid event cursor")
        clauses = ["event_index > ?"]
        values: list[object] = [after]
        if query.run_id is not None:
            clauses.append("run_id = ?")
            values.append(query.run_id)
        if query.attempt_id is not None:
            clauses.append("attempt_id = ?")
            values.append(query.attempt_id)
        if query.event_types:
            clauses.append("event_type IN (" + ",".join("?" for _ in query.event_types) + ")")
            values.extend(query.event_types)
        if query.producer_kinds:
            clauses.append("producer_kind IN (" + ",".join("?" for _ in query.producer_kinds) + ")")
            values.extend(kind.value for kind in query.producer_kinds)
        values.append(query.limit + 1)
        where = " AND ".join(clauses)
        statement = f"SELECT * FROM events WHERE {where} ORDER BY event_index LIMIT ?"
        with closing(self._connect()) as connection:
            rows = connection.execute(statement, values).fetchall()
        has_more = len(rows) > query.limit
        selected = rows[: query.limit]
        items = tuple(self._decode_event(row) for row in selected)
        next_cursor = str(selected[-1]["event_index"]) if has_more and selected else None
        return EventPage(items, next_cursor)

    def read_trace(self, attempt_id: str) -> TraceGraph:
        events: list[EventEnvelope] = []
        cursor: str | None = None
        while True:
            page = self.read_events(EventQuery(attempt_id=attempt_id, limit=10_000), cursor)
            events.extend(page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        grouped: dict[str, list[EventEnvelope]] = {}
        for event in events:
            if event.span_id is not None:
                grouped.setdefault(event.span_id, []).append(event)
        spans = tuple(
            TraceSpan(
                span_id,
                next((item.parent_span_id for item in items if item.parent_span_id), None),
                tuple(item.event_id for item in items),
            )
            for span_id, items in sorted(grouped.items())
        )
        return TraceGraph(attempt_id, tuple(events), spans)

    def get_artifact(self, artifact_id: str) -> ArtifactRef:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT artifacts.*,blobs.size_bytes AS manifest_size,
                          blobs.media_type AS manifest_media_type
                   FROM artifacts JOIN blobs ON blobs.digest=artifacts.manifest_digest
                   WHERE artifact_id=?""",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return self._decode_artifact(row)

    def list_artifacts(self, attempt_id: str) -> tuple[ArtifactRef, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT artifacts.*,blobs.size_bytes AS manifest_size,
                          blobs.media_type AS manifest_media_type
                   FROM artifacts JOIN blobs ON blobs.digest=artifacts.manifest_digest
                   WHERE attempt_id=? ORDER BY created_at,artifact_id""",
                (attempt_id,),
            ).fetchall()
        return tuple(self._decode_artifact(row) for row in rows)

    def open_blob(self, ref: BlobRef) -> BinaryIO:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT size_bytes,media_type,relative_path FROM blobs WHERE digest=?",
                (ref.digest,),
            ).fetchone()
        if row is None:
            raise KeyError(ref.digest)
        if row["size_bytes"] != ref.size_bytes or row["media_type"] != ref.media_type:
            raise ValueError("blob reference metadata does not match stored content")
        path = self.root / str(row["relative_path"])
        if not path.resolve().is_relative_to(self.blob_root.resolve()) or path.is_symlink():
            raise RuntimeError("invalid stored blob path")
        return path.open("rb")

    def _put_blob(self, data: bytes, media_type: str) -> BlobRef:
        if not media_type.strip():
            raise ValueError("blob media type must not be empty")
        hexadecimal = hashlib.sha256(data).hexdigest()
        digest = "sha256:" + hexadecimal
        path = self.blob_root / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal
        relative = path.relative_to(self.root).as_posix()
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not path.exists():
                descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".blob-")
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    temporary.chmod(0o400)
                    try:
                        temporary.replace(path)
                    except FileExistsError:
                        temporary.unlink(missing_ok=True)
                finally:
                    temporary.unlink(missing_ok=True)
            elif path.stat().st_size != len(data):
                raise RuntimeError("content-addressed blob size mismatch")
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT size_bytes,media_type FROM blobs WHERE digest=?", (digest,)
                ).fetchone()
                if row is not None and row["size_bytes"] != len(data):
                    raise RuntimeError("stored blob metadata mismatch")
                connection.execute(
                    """INSERT OR IGNORE INTO blobs(
                           digest,size_bytes,media_type,relative_path,created_at
                       ) VALUES (?,?,?,?,?)""",
                    (digest, len(data), media_type, relative, _now().isoformat()),
                )
                connection.commit()
                stored_media_type = str(row["media_type"]) if row is not None else media_type
        return BlobRef(digest, len(data), stored_media_type)

    def _decode_run_manifest(self, encoded: str) -> RunManifest:
        data = _mapping(encoded)
        policy = cast(dict[str, object], data["recording_policy"])
        from agent_infra.records.api import RecordingMode, RecordingPolicy

        return RunManifest(
            str(data["run_id"]),
            datetime.fromisoformat(str(data["created_at"])),
            cast(dict[str, object], data["request"]),
            RecordingPolicy(
                mode=RecordingMode(str(policy["mode"])),
                durability_before_cleanup=DurabilityLevel(str(policy["durability_before_cleanup"])),
                capture_agent_native=bool(policy["capture_agent_native"]),
                capture_stdout_stderr=bool(policy["capture_stdout_stderr"]),
                capture_resource_samples=bool(policy["capture_resource_samples"]),
                stream_bytes_per_job=int(cast(int, policy["stream_bytes_per_job"])),
                total_bytes_per_attempt=int(cast(int, policy["total_bytes_per_attempt"])),
            ),
        )

    def _decode_attempt_manifest(self, encoded: str) -> AttemptManifest:
        data = _mapping(encoded)
        return AttemptManifest(
            str(data["attempt_id"]),
            str(data["run_id"]),
            datetime.fromisoformat(str(data["started_at"])),
            str(data["task_id"]) if data.get("task_id") is not None else None,
            str(data["task_digest"]) if data.get("task_digest") is not None else None,
            cast(dict[str, object], data["policy_snapshot"]),
            cast(dict[str, object], data["environment_snapshot"]),
            {
                str(key): str(value)
                for key, value in cast(dict[str, object], data["coverage"]).items()
            },
        )

    def _decode_attempt(self, row: sqlite3.Row) -> AttemptRecord:
        return AttemptRecord(
            self._decode_attempt_manifest(row["manifest_json"]),
            str(row["status"]),
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            _mapping(row["result_json"]) if row["result_json"] else None,
        )

    def _decode_event(self, row: sqlite3.Row) -> EventEnvelope:
        links_data = json.loads(row["links_json"])
        links = tuple(
            EventLink(str(item["relation"]), item.get("span_id"), item.get("event_id"))
            for item in links_data
        )
        return EventEnvelope(
            str(row["schema_version"]),
            str(row["event_id"]),
            int(row["event_index"]),
            str(row["event_type"]),
            RecordContext(
                str(row["run_id"]),
                str(row["attempt_id"]),
                str(row["producer_id"]),
                ProducerKind(str(row["producer_kind"])),
                str(row["phase_id"]) if row["phase_id"] is not None else None,
                str(row["session_id"]) if row["session_id"] is not None else None,
            ),
            int(row["producer_sequence"]),
            datetime.fromisoformat(str(row["observed_at"])),
            datetime.fromisoformat(str(row["ingested_at"])),
            str(row["payload_schema"]),
            _mapping(row["payload_json"]),
            str(row["trace_id"]) if row["trace_id"] is not None else None,
            str(row["span_id"]) if row["span_id"] is not None else None,
            str(row["parent_span_id"]) if row["parent_span_id"] is not None else None,
            links,
            {str(key): str(value) for key, value in _mapping(row["correlation_json"]).items()},
            _strings(row["raw_refs_json"]),
            _strings(row["artifact_refs_json"]),
            Visibility(str(row["visibility"])),
            DataClass(str(row["data_class"])),
            CaptureStatus(str(row["capture_status"])),
            str(row["normalizer_name"]) if row["normalizer_name"] is not None else None,
            str(row["normalizer_version"]) if row["normalizer_version"] is not None else None,
            str(row["idempotency_key"]),
        )

    def _decode_artifact(self, row: sqlite3.Row) -> ArtifactRef:
        manifest = BlobRef(
            str(row["manifest_digest"]),
            int(row["manifest_size"]),
            str(row["manifest_media_type"]),
        )
        return ArtifactRef(
            str(row["artifact_id"]),
            str(row["name"]),
            str(row["kind"]),
            str(row["digest"]),
            int(row["size_bytes"]),
            str(row["media_type"]),
            manifest,
            Visibility(str(row["visibility"])),
            DataClass(str(row["data_class"])),
        )


class _LocalRecordSink:
    def __init__(self, store: LocalRecordsStore, context: RecordContext) -> None:
        self._store = store
        self._context = context

    @property
    def context(self) -> RecordContext:
        return self._context

    def append_events(self, events: Sequence[EventDraft]) -> WriteReceipt:
        if not events:
            return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, 0)
        identifiers: list[str] = []
        accepted = 0
        with self._store._lock, closing(self._store._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_sequence FROM producer_sequences WHERE producer_id=?",
                (self.context.producer_id,),
            ).fetchone()
            next_sequence = int(row["next_sequence"]) if row is not None else 0
            for draft in events:
                sequence = draft.producer_sequence
                if sequence is None:
                    sequence = next_sequence
                    next_sequence += 1
                else:
                    next_sequence = max(next_sequence, sequence + 1)
                idempotency_key = draft.idempotency_key or f"{self.context.producer_id}:{sequence}"
                payload_json = _dumps(draft.payload)
                existing = connection.execute(
                    """SELECT event_id,event_type,producer_id,producer_sequence,payload_json
                       FROM events WHERE idempotency_key=?""",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    identity = (
                        draft.event_type,
                        self.context.producer_id,
                        sequence,
                        payload_json,
                    )
                    stored = (
                        existing["event_type"],
                        existing["producer_id"],
                        existing["producer_sequence"],
                        existing["payload_json"],
                    )
                    if stored != identity:
                        raise ValueError("idempotency key already identifies another event")
                    identifiers.append(str(existing["event_id"]))
                    continue
                event_id = "evt_" + uuid.uuid4().hex
                observed_at = draft.observed_at or _now()
                ingested_at = _now()
                connection.execute(
                    """INSERT INTO events(
                           event_id,schema_version,event_type,run_id,attempt_id,phase_id,session_id,
                           producer_id,producer_kind,producer_sequence,observed_at,ingested_at,
                           payload_schema,payload_json,trace_id,span_id,parent_span_id,links_json,
                           correlation_json,raw_refs_json,artifact_refs_json,visibility,data_class,
                           capture_status,normalizer_name,normalizer_version,idempotency_key
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        "records.event.v1",
                        draft.event_type,
                        self.context.run_id,
                        self.context.attempt_id,
                        self.context.phase_id,
                        self.context.session_id,
                        self.context.producer_id,
                        self.context.producer_kind.value,
                        sequence,
                        observed_at.isoformat(),
                        ingested_at.isoformat(),
                        draft.payload_schema,
                        payload_json,
                        draft.trace_id,
                        draft.span_id,
                        draft.parent_span_id,
                        _dumps([asdict(link) for link in draft.links]),
                        _dumps(draft.correlation),
                        _dumps(draft.raw_refs),
                        _dumps(draft.artifact_refs),
                        draft.visibility.value,
                        draft.data_class.value,
                        draft.capture_status.value,
                        draft.normalizer_name,
                        draft.normalizer_version,
                        idempotency_key,
                    ),
                )
                identifiers.append(event_id)
                accepted += 1
            connection.execute(
                """INSERT INTO producer_sequences(producer_id,next_sequence) VALUES (?,?)
                   ON CONFLICT(producer_id) DO UPDATE SET next_sequence=excluded.next_sequence""",
                (self.context.producer_id, next_sequence),
            )
            connection.commit()
        return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, accepted, tuple(identifiers))

    def put_blob(self, data: bytes, *, media_type: str) -> BlobRef:
        return self._store._put_blob(data, media_type)

    def start_stream(
        self,
        stream_id: str,
        name: str,
        *,
        media_type: str = "application/octet-stream",
        visibility: Visibility = Visibility.CONTROLLER,
        data_class: DataClass = DataClass.INTERNAL,
    ) -> None:
        if not stream_id.strip() or not name.strip() or not media_type.strip():
            raise ValueError("stream identity and media type must not be empty")
        filename = hashlib.sha256(stream_id.encode()).hexdigest() + ".part"
        spool = self._store.spool_root / filename
        with self._store._lock, closing(self._store._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM streams WHERE stream_id=?", (stream_id,)
            ).fetchone()
            expected = (
                self.context.run_id,
                self.context.attempt_id,
                self.context.producer_id,
                name,
                media_type,
                visibility.value,
                data_class.value,
            )
            if row is not None:
                actual = tuple(
                    row[key]
                    for key in (
                        "run_id",
                        "attempt_id",
                        "producer_id",
                        "name",
                        "media_type",
                        "visibility",
                        "data_class",
                    )
                )
                if actual != expected:
                    raise ValueError("stream ID already has different metadata")
                return
            spool.touch(mode=0o600, exist_ok=False)
            connection.execute(
                """INSERT INTO streams(
                       stream_id,run_id,attempt_id,producer_id,name,media_type,visibility,
                       data_class,spool_path,size_bytes,capture_status
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stream_id,
                    *expected,
                    spool.relative_to(self._store.root).as_posix(),
                    0,
                    CaptureStatus.PARTIAL.value,
                ),
            )
            connection.commit()

    def append_stream(self, stream_id: str, chunk: bytes, offset: int) -> WriteReceipt:
        if offset < 0:
            raise ValueError("stream offset must be non-negative")
        with self._store._lock, closing(self._store._connect()) as connection:
            row = connection.execute(
                "SELECT spool_path,size_bytes,blob_digest FROM streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if row is None:
                raise KeyError(stream_id)
            if row["blob_digest"] is not None:
                raise ValueError("stream is already finalized")
            size = int(row["size_bytes"])
            path = self._store.root / str(row["spool_path"])
            if offset < size:
                with path.open("rb") as stream:
                    stream.seek(offset)
                    if stream.read(len(chunk)) != chunk or offset + len(chunk) > size:
                        raise ValueError("stream retry does not match stored bytes")
                return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, 0, (stream_id,))
            if offset != size:
                raise ValueError("stream append offset is not contiguous")
            with path.open("ab") as stream:
                stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            connection.execute(
                "UPDATE streams SET size_bytes=? WHERE stream_id=?", (size + len(chunk), stream_id)
            )
            connection.commit()
        return WriteReceipt(DurabilityLevel.DURABLE_LOCAL, len(chunk), (stream_id,))

    def finalize_stream(
        self, stream_id: str, status: CaptureStatus = CaptureStatus.COMPLETE
    ) -> StreamRef:
        with self._store._lock, closing(self._store._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM streams WHERE stream_id=?", (stream_id,)
            ).fetchone()
            if row is None:
                raise KeyError(stream_id)
            if row["blob_digest"] is not None:
                blob_row = connection.execute(
                    "SELECT size_bytes,media_type FROM blobs WHERE digest=?", (row["blob_digest"],)
                ).fetchone()
                assert blob_row is not None
                return StreamRef(
                    stream_id,
                    str(row["name"]),
                    BlobRef(
                        str(row["blob_digest"]),
                        int(blob_row["size_bytes"]),
                        str(blob_row["media_type"]),
                    ),
                    int(row["size_bytes"]),
                    CaptureStatus(str(row["capture_status"])),
                )
            path = self._store.root / str(row["spool_path"])
            data = path.read_bytes()
            blob = self._store._put_blob(data, str(row["media_type"]))
            connection.execute(
                "UPDATE streams SET blob_digest=?,capture_status=? WHERE stream_id=?",
                (blob.digest, status.value, stream_id),
            )
            connection.commit()
            path.unlink(missing_ok=True)
            return StreamRef(stream_id, str(row["name"]), blob, len(data), status)

    def commit_artifact(
        self,
        path: Path,
        *,
        name: str,
        media_type: str = "application/octet-stream",
        visibility: Visibility = Visibility.USER,
        data_class: DataClass = DataClass.USER_PRIVATE,
    ) -> ArtifactRef:
        resolved = path.resolve()
        if path.is_symlink() or not path.exists() or not name.strip():
            raise ValueError("artifact must be an existing regular file or directory")
        digest = content_digest(path)
        files: list[dict[str, object]] = []
        total = 0
        if path.is_file():
            candidates = [(path.name, path)]
            kind = "file"
        elif path.is_dir():
            candidates = [
                (item.relative_to(path).as_posix(), item)
                for item in sorted(path.rglob("*"))
                if item.is_file()
            ]
            kind = "directory"
        else:
            raise ValueError("artifact must be a regular file or directory")
        parent = resolved if path.is_dir() else resolved.parent
        for relative, item in candidates:
            if item.is_symlink() or not item.resolve().is_relative_to(parent):
                raise ValueError("artifact contains an unsupported path")
            data = item.read_bytes()
            item_media_type = media_type if kind == "file" else "application/octet-stream"
            blob = self.put_blob(data, media_type=item_media_type)
            total += len(data)
            files.append({"path": relative, "size_bytes": len(data), "blob": asdict(blob)})
        manifest_data = _dumps(
            {
                "schema_version": "records.artifact_manifest.v1",
                "kind": kind,
                "digest": digest,
                "files": files,
            }
        ).encode()
        manifest = self.put_blob(
            manifest_data, media_type="application/vnd.agent-infra.artifact+json"
        )
        artifact_id = "artifact_" + uuid.uuid4().hex
        with self._store._lock, closing(self._store._connect()) as connection:
            connection.execute(
                """INSERT INTO artifacts(
                       artifact_id,run_id,attempt_id,producer_id,name,kind,digest,size_bytes,
                       media_type,manifest_digest,visibility,data_class,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    artifact_id,
                    self.context.run_id,
                    self.context.attempt_id,
                    self.context.producer_id,
                    name,
                    kind,
                    digest,
                    total,
                    media_type,
                    manifest.digest,
                    visibility.value,
                    data_class.value,
                    _now().isoformat(),
                ),
            )
            connection.commit()
        return ArtifactRef(
            artifact_id, name, kind, digest, total, media_type, manifest, visibility, data_class
        )


class LocalRunJournal:
    """Compatibility writer for legacy callers; new Run code uses LocalRecordsStore."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def event(self, kind: str, **fields: Any) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": _now().isoformat(), "kind": kind, **fields}) + "\n")

    def finish(self, result: dict[str, Any]) -> None:
        temporary = self.root / "result.tmp"
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.replace(self.root / "result.json")
