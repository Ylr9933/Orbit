"""Exercise the actual stdlib supervisor without Docker; never calls a model."""

import base64
import sys
import time
from pathlib import Path

import pytest

from agent_infra.environments import _research_runtime as runtime


def wait_job(job):
    job.thread.join(4)
    assert not job.thread.is_alive()
    return job.status()


def test_safe_files_refuse_symlinks_special_files_and_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", str(tmp_path))
    runtime.file_operation({"operation": "write", "path": "code/a.py", "text": "print(1)"})
    assert runtime.file_operation({"operation": "read", "path": "code/a.py"})["text"] == "print(1)"
    (tmp_path / "link").symlink_to("/tmp")
    for path in ("../secret", "/etc/passwd", "link/secret"):
        with pytest.raises((OSError, ValueError)):
            runtime.file_operation({"operation": "read", "path": path})
    (tmp_path / "direct").symlink_to(tmp_path / "code/a.py")
    with pytest.raises(OSError):
        runtime.file_operation({"operation": "write", "path": "direct", "text": "corrupt"})
    assert (tmp_path / "code/a.py").read_text() == "print(1)"


def test_job_timeout_children_and_log_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", str(tmp_path))
    monkeypatch.setattr(runtime, "LOG_LIMIT", 100)
    job = runtime.Job(
        {
            "job_id": "one",
            "argv": [
                sys.executable,
                "-c",
                'import time; print("x"*200, flush=True); time.sleep(10)',
            ],
            "cwd": ".",
            "timeout_seconds": 0.15,
        }
    )
    assert wait_job(job)["state"] == "timed_out"
    assert len(job.output) == 100 and job.truncated
    # Shell exits but its child would otherwise retain the stdout pipe for 20 seconds.
    job = runtime.Job(
        {
            "job_id": "two",
            "argv": ["/bin/sh", "-c", "sleep 20 & echo done"],
            "cwd": ".",
            "timeout_seconds": 5,
        }
    )
    assert wait_job(job)["state"] == "completed"


def test_runtime_retry_and_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", str(tmp_path))
    instance = runtime.Runtime()
    request = {
        "action": "start",
        "job_id": "one",
        "argv": [sys.executable, "-c", 'print("hello")'],
        "cwd": ".",
        "timeout_seconds": 5,
    }
    instance.dispatch(request)
    wait_job(instance.jobs["one"])
    instance.dispatch(request)
    assert len(instance.jobs) == 1
    response = instance.dispatch({"action": "logs", "job_id": "one", "cursor": 0})
    assert base64.b64decode(response["content_base64"]) == b"hello\n"
    assert (
        instance.dispatch({"action": "logs", "job_id": "one", "cursor": response["next_cursor"]})[
            "text"
        ]
        == ""
    )


def test_stop_kills_running_child_in_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", str(tmp_path))
    job = runtime.Job(
        {
            "job_id": "children",
            "argv": ["/bin/sh", "-c", "sleep 120 & echo $!; wait"],
            "cwd": ".",
            "timeout_seconds": 10,
        }
    )
    deadline = time.monotonic() + 2
    while not job.output:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    pid = int(bytes(job.output).strip())
    job.stop_requested.set()
    assert wait_job(job)["state"] == "cancelled"
    status = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 2
    while True:
        try:
            state = status.read_text().split()[2]
        except (FileNotFoundError, ProcessLookupError):
            break  # The kernel already reaped the killed child.
        if state in {"Z", "X"}:
            break
        assert time.monotonic() < deadline, f"child still alive: {state}"
        time.sleep(0.01)


def test_closed_output_does_not_disable_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", str(tmp_path))
    job = runtime.Job(
        {
            "job_id": "closed-output",
            "argv": [
                sys.executable,
                "-c",
                "import os,time; os.close(1); os.close(2); time.sleep(120)",
            ],
            "cwd": ".",
            "timeout_seconds": 0.15,
        }
    )
    assert wait_job(job)["state"] == "timed_out"
