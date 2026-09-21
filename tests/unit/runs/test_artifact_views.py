"""Real local Records + bounded views; no execution backend or model needed."""

import base64
from datetime import UTC, datetime

import pytest

from agent_infra.records import AttemptManifest, ProducerKind, RecordContext, RunManifest
from agent_infra.records.api import DataClass
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.control_store import RunControlStore
from agent_infra.runs.query import RunQueries


def seed_artifacts(root, commands, records):
    run = commands.create("read-fixture", {"kind": "research"}, {"project_id": "project"})
    now = datetime.now(UTC)
    records.begin_run(RunManifest(run["run_id"], now, {}))
    records.begin_attempt(AttemptManifest(run["attempt_id"], run["run_id"], now))
    commands.update(run["run_id"], state="finished")
    sink = records.scoped_sink(
        RecordContext(run["run_id"], run["attempt_id"], "fixture", ProducerKind.RUN)
    )
    counter = 0

    def save(data, name="summary.json", **kwargs):
        nonlocal counter
        counter += 1
        workspace = root / str(counter)
        file = workspace / name
        file.parent.mkdir(parents=True)
        file.write_bytes(data)
        artifact = sink.commit_artifact(workspace, name="test-artifact", **kwargs)
        return artifact.artifact_id

    return run["run_id"], save


@pytest.fixture
def views(tmp_path):
    commands = RunControlStore(tmp_path / "controller")
    records = LocalRecordsStore(tmp_path / "records")
    run_id, save = seed_artifacts(tmp_path / "source", commands, records)
    return RunQueries(commands, records), run_id, save


def test_json_default_is_readable_and_legacy_download_unchanged(views):
    queries, run, save = views
    data = '{"结果": "成功", "mse": 0.01}\n'.encode()
    artifact = save(data)
    result = queries.artifact_view(run, artifact, "summary.json")
    assert result["text"].encode() == data
    assert result["format"] == "text" and result["eof"]
    assert not result["truncated"] and result["next_offset"] is None
    assert "content_base64" not in result
    assert result["digest"].startswith("sha256:")
    assert (
        base64.b64decode(queries.artifact(run, artifact, "summary.json")["content_base64"]) == data
    )
    assert queries.artifact_view(run, artifact)["files"] == [
        {"path": "summary.json", "size_bytes": len(data)}
    ]


@pytest.mark.parametrize("limit", [4, 5, 7, 16, 16384])
def test_utf8_pages_reconstruct_exactly_with_forward_progress(views, limit):
    queries, run, save = views
    text = "中文实验🙂\r\n结果\t0.25\n" * 15
    artifact = save(text.encode(), "trial.log")
    offset, parts = 0, []
    while offset is not None:
        result = queries.artifact_view(run, artifact, "trial.log", offset=offset, limit=limit)
        parts.append(result["text"])
        assert 0 < result["bytes_read"] <= limit
        assert result["bytes_read"] == len(result["text"].encode())
        assert result["truncated"] == (not result["eof"])
        if result["next_offset"] is not None:
            assert result["next_offset"] > offset
        offset = result["next_offset"]
    assert "".join(parts) == text


def test_empty_file_eof_and_invalid_utf8_offset(views):
    queries, run, save = views
    empty = save(b"", "empty.txt")
    result = queries.artifact_view(run, empty, "empty.txt")
    assert result["text"] == "" and result["eof"] and result["bytes_read"] == 0
    artifact = save("中文🙂".encode())
    with pytest.raises(ValueError, match="UTF-8"):
        queries.artifact_view(run, artifact, "summary.json", format="text", offset=1)
    end = queries.artifact_view(run, artifact, "summary.json", offset=10)
    assert end["text"] == "" and end["next_offset"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"offset": -1},
        {"offset": True},
        {"offset": 1000},
        {"limit": 0},
        {"limit": True},
        {"limit": 65537},
        {"format": "unknown"},
    ],
)
def test_invalid_ranges_fail(views, kwargs):
    queries, run, save = views
    artifact = save(b"{}")
    with pytest.raises(ValueError):
        queries.artifact_view(run, artifact, "summary.json", **kwargs)


@pytest.mark.parametrize(
    "name,data",
    [
        ("weights.pt", b"even ASCII weights stay binary"),
        ("archive.zip", b"PK\x03\x04\x00"),
        ("invalid.json", b"\xff\x00"),
    ],
)
def test_binary_metadata_and_explicit_lossless_base64(views, name, data):
    queries, run, save = views
    artifact = save(data, name)
    result = queries.artifact_view(run, artifact, name)
    assert result["kind"] == "binary" and result["format"] == "metadata"
    assert "text" not in result and "content_base64" not in result
    assert result["download"]["requires_auth"]
    decoded, offset = b"", 0
    while offset is not None:
        page = queries.artifact_view(run, artifact, name, format="base64", offset=offset, limit=5)
        decoded += base64.b64decode(page["content_base64"])
        offset = page["next_offset"]
    assert decoded == data


def test_bad_utf8_after_detection_window_is_not_silently_replaced(views):
    queries, run, save = views
    artifact = save(b"x" * 5000 + b"\xff", "result.txt")
    result = queries.artifact_view(run, artifact, "result.txt")
    assert result["format"] == "metadata" and "text" not in result
    assert "UTF-8" in result["reason"]


def test_large_artifact_can_be_paged_without_whole_file_download(views):
    queries, run, save = views
    artifact = save(b"a" * (16 * 1024**2 + 1), "big.txt")
    result = queries.artifact_view(run, artifact, "big.txt", offset=16 * 1024**2, limit=4)
    assert result["text"] == "a" and result["eof"]
    assert not result["download"]["available"]
    with pytest.raises(ValueError, match="16 MiB"):
        queries.artifact(run, artifact, "big.txt")


def test_views_keep_run_visibility_and_exact_member_checks(views):
    queries, run, save = views
    artifact = save(b"{}")
    private = save(b"private", data_class=DataClass.PRIVATE_EVALUATION)
    for mode in ("auto", "text", "base64", "metadata"):
        with pytest.raises(KeyError):
            queries.artifact_view(run, private, "summary.json", format=mode)
        with pytest.raises(KeyError):
            queries.artifact_view("other-run", artifact, "summary.json", format=mode)
        with pytest.raises(KeyError):
            queries.artifact_view(run, artifact, "../summary.json", format=mode)


def test_size_mismatch_detected_even_for_metadata(views):
    queries, run, save = views
    artifact = save(b"{}")
    result = queries.artifact_view(run, artifact, "summary.json")
    digest = result["digest"].removeprefix("sha256:")
    blob = queries.records.blob_root / digest[:2] / digest[2:4] / digest
    blob.chmod(0o600)  # Deliberately corrupt only this test's normally read-only CAS fixture.
    blob.write_bytes(b"changed")
    with pytest.raises(ValueError, match="size mismatch"):
        queries.artifact_view(run, artifact, "summary.json", format="metadata")
