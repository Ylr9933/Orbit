"""Scoped event, stream and artifact writes for the local Records backend."""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Sequence
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from agent_infra.contracts.files import content_digest
from agent_infra.records._serialization import _dumps, _now
from agent_infra.records.api import (
    ArtifactRef,
    BlobRef,
    CaptureStatus,
    DataClass,
    DurabilityLevel,
    EventDraft,
    RecordContext,
    StreamRef,
    Visibility,
    WriteReceipt,
)

if TYPE_CHECKING:
    from agent_infra.records.local import LocalRecordsStore


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
            connection.execute("BEGIN IMMEDIATE")
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
            # An interrupted creation may leave an uncommitted spool. No row means
            # no accepted bytes; recover that file without inventing a second stream.
            descriptor = os.open(
                spool, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            descriptor = os.open(spool.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
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
            connection.execute("BEGIN IMMEDIATE")
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
            with path.open("r+b") as stream:
                if os.fstat(stream.fileno()).st_size < size:
                    raise ValueError("stream spool is shorter than its committed cursor")
                # A crash can happen after fsync but before the SQLite cursor commit.
                # Only committed bytes are authoritative; the producer resends the rest.
                stream.truncate(size)
                stream.seek(size)
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
            with path.open("rb") as source:
                data = source.read(int(row["size_bytes"]))
            if len(data) != int(row["size_bytes"]):
                raise ValueError("stream spool is shorter than its committed cursor")
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
            item_media_type = media_type if kind == "file" else "application/octet-stream"
            blob = self._store._put_blob_file(item, item_media_type)
            total += blob.size_bytes
            files.append({"path": relative, "size_bytes": blob.size_bytes, "blob": asdict(blob)})
        if content_digest(path) != digest:
            raise ValueError("artifact source changed during durable transfer")
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
