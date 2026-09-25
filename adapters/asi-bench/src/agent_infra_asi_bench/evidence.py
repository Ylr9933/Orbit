"""Freeze only ASI-Bench-declared Agent sidecars into bounded native evidence."""

import hashlib
import json
from pathlib import Path

SIDECARS = {
    "raw_stdout_file": "codex-stdout.jsonl",
    "raw_stderr_file": "codex-stderr.log",
    "trajectory_file": "trajectory.json",
    "model_calls_file": "model-calls.json",
}
MAX_FILE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 192 * 1024**2
MAX_VIEW_STEPS = 2000
MAX_VIEW_TEXT = 4000


def _copy_bounded(source: Path, target: Path, limit: int) -> tuple[int, str, bool]:
    digest = hashlib.sha256()
    count = 0
    with source.open("rb") as reader, target.open("xb") as writer:
        while count < limit:
            block = reader.read(min(1024**2, limit - count))
            if not block:
                break
            writer.write(block)
            digest.update(block)
            count += len(block)
    return count, "sha256:" + digest.hexdigest(), source.stat().st_size > count


def capture(result_path: Path, result: dict, destination: Path, *, docker: dict) -> dict:
    """Copy declared sidecars only; leave a coverage record for absent/oversized files."""
    destination.mkdir(mode=0o700)
    output = result.get("agent_output") or {}
    files: dict[str, dict] = {}
    remaining = MAX_TOTAL_BYTES
    for field, name in SIDECARS.items():
        declared = output.get(field)
        entry: dict = {"source_field": field, "capture_status": "unavailable"}
        if declared:
            if (
                not isinstance(declared, str)
                or declared != Path(declared).name
                or declared in {".", ".."}
            ):
                entry = {"source_field": field, "capture_status": "invalid_reference"}
            else:
                source = result_path.parent / declared
                if source.is_symlink() or not source.is_file():
                    entry = {"source_field": field, "capture_status": "missing"}
                else:
                    limit = min(MAX_FILE_BYTES, remaining)
                    size, digest, truncated = _copy_bounded(source, destination / name, limit)
                    remaining -= size
                    entry = {
                        "source_field": field,
                        "capture_status": "truncated" if truncated else "complete",
                        "member": "outputs/evidence/" + name,
                        "source_size_bytes": source.stat().st_size,
                        "size_bytes": size,
                        "digest": digest,
                    }
        files[field] = entry

    session_id = None
    completed_turns = 0
    last_usage = None
    stdout = destination / "codex-stdout.jsonl"
    if files["raw_stdout_file"]["capture_status"] == "complete":
        with stdout.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "thread.started" and isinstance(
                    event.get("thread_id"), str
                ):
                    session_id = event["thread_id"]
                if event.get("type") == "turn.completed":
                    completed_turns += 1
                    if isinstance(event.get("usage"), dict):
                        last_usage = event["usage"]

    trajectory: dict = {"capture_status": "unavailable", "total_steps": 0}
    source = destination / "trajectory.json"
    origin = "native"
    if (
        files["trajectory_file"]["capture_status"] == "unavailable"
        and files["raw_stdout_file"]["capture_status"] == "complete"
    ):
        from ai4sci_bench.trajectory.codex_extractor import extract_from_jsonl

        try:
            derived = extract_from_jsonl(
                stdout.read_text(encoding="utf-8", errors="replace"),
                result.get("instance_id", ""),
            )
            encoded = json.dumps([item.to_dict() for item in derived.steps]).encode()
            if len(encoded) > MAX_FILE_BYTES:
                files["trajectory_file"] = {
                    "source_field": "trajectory_file",
                    "capture_status": "too_large",
                }
            else:
                source.write_bytes(encoded)
                files["trajectory_file"] = {
                    "source_field": "trajectory_file",
                    "capture_status": "derived",
                    "member": "outputs/evidence/trajectory.json",
                    "size_bytes": len(encoded),
                    "digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
                }
                origin = "codex_extractor"
        except Exception:  # Native extractor failures must not discard raw evidence.
            files["trajectory_file"] = {
                "source_field": "trajectory_file",
                "capture_status": "extract_failed",
            }
    if files["trajectory_file"]["capture_status"] in {"complete", "derived"}:
        try:
            steps = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(steps, list):
                raise ValueError("native trajectory is not a list")
            clipped_content = sum(
                len(str(item.get("content", ""))) > MAX_VIEW_TEXT
                for item in steps[:MAX_VIEW_STEPS]
                if isinstance(item, dict)
            )
            view = [
                {
                    "step_index": item.get("step_index", index),
                    "timestamp_ms": item.get("timestamp_ms"),
                    "step_type": item.get("step_type", "unknown"),
                    "content": str(item.get("content", ""))[:MAX_VIEW_TEXT],
                    "metadata": {
                        key: value
                        for key, value in (item.get("metadata") or {}).items()
                        if key in {"role", "tool_name", "parent_tool_name", "is_error", "exit_code"}
                        and isinstance(value, (str, int, bool))
                    },
                }
                for index, item in enumerate(steps[:MAX_VIEW_STEPS])
                if isinstance(item, dict)
            ]
            (destination / "trajectory-view.json").write_text(
                json.dumps(view, ensure_ascii=False), encoding="utf-8"
            )
            trajectory = {
                "capture_status": (
                    "truncated" if len(steps) > MAX_VIEW_STEPS or clipped_content else "complete"
                ),
                "total_steps": len(steps),
                "view_steps": len(view),
                "content_truncated_steps": clipped_content,
                "native_summary": output.get("trajectory_summary") or {},
                "member": "outputs/evidence/trajectory-view.json",
                "origin": origin,
                "session_id": session_id,
            }
        except (ValueError, UnicodeError):
            trajectory = {"capture_status": "invalid", "total_steps": 0}

    overall = (
        "complete"
        if files["raw_stdout_file"]["capture_status"] == "complete"
        and trajectory["capture_status"] == "complete"
        else "partial"
    )
    index = {
        "schema_version": 1,
        "capture_status": overall,
        "files": files,
        "calls": {
            "completed_turns": completed_turns,
            "last_reported_usage": last_usage,
            "capture_status": "from_jsonl"
            if files["raw_stdout_file"]["capture_status"] == "complete"
            else "unavailable",
        },
        "trajectory": trajectory,
        "docker": docker,
    }
    (destination / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return index
