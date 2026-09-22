"""Durability, idempotency, query, stream, and artifact tests for local Records."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from agent_infra.records import (
    AttemptManifest,
    CaptureStatus,
    EventDraft,
    EventQuery,
    ProducerKind,
    RecordContext,
    RunManifest,
)
from agent_infra.records.local import LocalRecordsStore


def configured_store(tmp_path):
    store = LocalRecordsStore(tmp_path / "records")
    now = datetime.now(UTC)
    store.begin_run(RunManifest("run-1", now, {"kind": "test"}))
    store.begin_attempt(AttemptManifest("attempt-1", "run-1", now, "task-1", "sha256:x"))
    return store


def test_events_are_idempotent_queryable_and_reopenable(tmp_path):
    store = configured_store(tmp_path)
    sink = store.scoped_sink(RecordContext("run-1", "attempt-1", "controller-1", ProducerKind.RUN))
    draft = EventDraft(
        "attempt.started",
        {"status": "running"},
        producer_sequence=7,
        idempotency_key="start-once",
        span_id="attempt-span",
    )
    first = sink.append_events((draft,))
    repeated = sink.append_events((draft,))
    assert first.identifiers == repeated.identifiers
    assert first.accepted == 1 and repeated.accepted == 0
    with pytest.raises(ValueError, match="idempotency"):
        sink.append_events(
            (
                EventDraft(
                    "attempt.started",
                    {"status": "different"},
                    producer_sequence=7,
                    idempotency_key="start-once",
                ),
            )
        )

    sink.append_events((EventDraft("attempt.finished", {"status": "completed"}),))
    page = store.read_events(EventQuery(attempt_id="attempt-1", limit=1))
    assert [event.event_type for event in page.items] == ["attempt.started"]
    assert page.next_cursor is not None
    second = store.read_events(EventQuery(attempt_id="attempt-1", limit=1), page.next_cursor)
    assert [event.event_type for event in second.items] == ["attempt.finished"]
    assert second.next_cursor is None

    store.finish_attempt("attempt-1", status="completed", result={"score": 1})
    store.finish_run("run-1", status="completed")
    reopened = LocalRecordsStore(tmp_path / "records")
    assert reopened.get_run("run-1").status == "completed"
    assert reopened.get_attempt("attempt-1").result == {"score": 1}
    trace = reopened.read_trace("attempt-1")
    assert trace.spans[0].span_id == "attempt-span"


def test_streams_retry_offsets_and_artifacts_use_content_addressing(tmp_path):
    store = configured_store(tmp_path)
    sink = store.scoped_sink(
        RecordContext("run-1", "attempt-1", "environment-1", ProducerKind.ENVIRONMENT)
    )
    sink.start_stream("stdout-1", "stdout", media_type="text/plain")
    assert sink.append_stream("stdout-1", b"hello", 0).accepted == 5
    assert sink.append_stream("stdout-1", b"hello", 0).accepted == 0
    with pytest.raises(ValueError, match="contiguous"):
        sink.append_stream("stdout-1", b"!", 10)
    stream = sink.finalize_stream("stdout-1", CaptureStatus.TRUNCATED)
    assert stream.capture_status is CaptureStatus.TRUNCATED
    assert stream.blob is not None
    with store.open_blob(stream.blob) as source:
        assert source.read() == b"hello"

    output = tmp_path / "output"
    output.mkdir()
    (output / "result.txt").write_text("answer")
    (output / "nested").mkdir()
    (output / "nested" / "metrics.json").write_text('{"loss":0.1}')
    artifact = sink.commit_artifact(output, name="solver-submission")
    assert artifact.kind == "directory" and artifact.size_bytes > 0
    assert store.get_artifact(artifact.artifact_id) == artifact
    assert store.list_artifacts("attempt-1") == (artifact,)
    with store.open_blob(artifact.manifest_blob) as source:
        assert b"records.artifact_manifest.v1" in source.read()


@pytest.mark.parametrize("resume_append", [True, False])
def test_stream_crash_tail_is_not_duplicated_or_finalized(tmp_path, resume_append):
    store = configured_store(tmp_path)
    context = RecordContext("run-1", "attempt-1", "controller-1", ProducerKind.RUN)
    sink = store.scoped_sink(context)
    sink.start_stream("crash", "stdout")
    sink.append_stream("crash", b"accepted", 0)
    spool = tmp_path / "records/spool" / (hashlib.sha256(b"crash").hexdigest() + ".part")
    # Emulate fsynced file bytes whose SQLite cursor transaction never committed.
    with spool.open("ab") as output:
        output.write(b"uncommitted")
    recovered = LocalRecordsStore(tmp_path / "records").scoped_sink(context)
    if resume_append:
        recovered.append_stream("crash", b"resent", len(b"accepted"))
    ref = recovered.finalize_stream("crash")
    with store.open_blob(ref.blob) as source:
        assert source.read() == b"accepted" + (b"resent" if resume_append else b"")


def test_stream_creation_crash_and_truncated_committed_spool(tmp_path):
    store = configured_store(tmp_path)
    sink = store.scoped_sink(RecordContext("run-1", "attempt-1", "controller-1", ProducerKind.RUN))
    spool = tmp_path / "records/spool" / (hashlib.sha256(b"new").hexdigest() + ".part")
    spool.touch()  # File created, row not committed.
    sink.start_stream("new", "stdout")
    sink.append_stream("new", b"accepted", 0)
    spool.write_bytes(b"short")  # Data loss must fail, rather than manufacture missing bytes.
    with pytest.raises(ValueError, match="shorter"):
        sink.append_stream("new", b"more", len(b"accepted"))
    with pytest.raises(ValueError, match="shorter"):
        sink.finalize_stream("new")


def test_independent_producers_can_append_concurrently(tmp_path):
    store = configured_store(tmp_path)

    def write(producer: int) -> None:
        sink = store.scoped_sink(
            RecordContext("run-1", "attempt-1", f"worker-{producer}", ProducerKind.ENVIRONMENT)
        )
        for index in range(20):
            sink.append_events((EventDraft("resource.sampled", {"sample": index}),))

    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(write, range(4)))
    page = store.read_events(EventQuery(attempt_id="attempt-1", limit=100))
    assert len(page.items) == 80
    assert len({event.event_id for event in page.items}) == 80
    for producer in range(4):
        sequences = [
            event.producer_sequence
            for event in page.items
            if event.context.producer_id == f"worker-{producer}"
        ]
        assert sequences == list(range(20))
