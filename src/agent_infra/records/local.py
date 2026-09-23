"""SQLite metadata, content-addressed blobs and reads for local execution."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import BinaryIO, cast

from agent_infra.contracts.files import resume_copy_file
from agent_infra.records._local_sink import _LocalRecordSink
from agent_infra.records._serialization import _dumps, _mapping, _now, _strings
from agent_infra.records.api import (
    ArtifactRef,
    AttemptManifest,
    AttemptRecord,
    BlobRef,
    CaptureStatus,
    DataClass,
    DurabilityLevel,
    EventEnvelope,
    EventLink,
    EventPage,
    EventQuery,
    ProducerKind,
    RecordContext,
    RunManifest,
    RunRecord,
    TraceGraph,
    TraceSpan,
    Visibility,
    WriteReceipt,
)
from agent_infra.records.legacy import LocalRunJournal as LocalRunJournal

_SCHEMA_VERSION = 1


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

    def _put_blob_file(self, source: Path, media_type: str) -> BlobRef:
        """Import a large file with durable partial bytes and bounded memory."""
        if source.is_symlink() or not source.is_file() or not media_type.strip():
            raise ValueError("blob source must be a regular file with a media type")
        with source.open("rb") as stream:
            hexadecimal = hashlib.file_digest(stream, "sha256").hexdigest()
        size = source.stat().st_size
        path = self.blob_root / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal
        digest = "sha256:" + hexadecimal
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = path.with_suffix(".lock")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with self._lock:
                if path.is_symlink():
                    raise RuntimeError("stored blob path is a symlink")
                if not path.exists():
                    partial = path.with_suffix(".part")
                    if partial.exists():
                        if partial.is_symlink() or not partial.is_file():
                            raise RuntimeError("stored partial blob is not a regular file")
                        partial.chmod(0o600)
                    resume_copy_file(source, partial)
                    with partial.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != hexadecimal:
                            raise ValueError("blob source changed during transfer")
                    partial.chmod(0o400)
                    partial.replace(path)
                    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                else:
                    with path.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != hexadecimal:
                            raise RuntimeError("stored content-addressed blob changed")
                if path.stat().st_size != size:
                    raise RuntimeError("stored blob size differs from source")
                with closing(self._connect()) as connection:
                    row = connection.execute(
                        "SELECT size_bytes,media_type FROM blobs WHERE digest=?", (digest,)
                    ).fetchone()
                    if row is not None and int(row["size_bytes"]) != size:
                        raise RuntimeError("stored blob metadata mismatch")
                    connection.execute(
                        """INSERT OR IGNORE INTO blobs(
                               digest,size_bytes,media_type,relative_path,created_at
                           ) VALUES (?,?,?,?,?)""",
                        (
                            digest,
                            size,
                            media_type,
                            path.relative_to(self.root).as_posix(),
                            _now().isoformat(),
                        ),
                    )
                    connection.commit()
                    stored_media = str(row["media_type"]) if row is not None else media_type
        finally:
            os.close(fd)
        return BlobRef(digest, size, stored_media)

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
