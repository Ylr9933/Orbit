"""Standalone stdlib supervisor copied read-only into the research container.

No host imports or host credentials. Runs as the container's unprivileged UID.
The runtime is for cooperative research code, not isolation between hostile Jobs.
"""

import base64
import json
import math
import os
import selectors
import signal
import socketserver
import stat
import subprocess
import threading
import time
from pathlib import PurePosixPath
from typing import Any

ROOT = "/workspace"
SOCKET = "/tmp/agent-infra-research.sock"
LOG_LIMIT = 8 * 1024**2


def open_path(
    path: str, *, flags: int = os.O_RDONLY, directory: bool = False, create: bool = False
) -> int:
    """Walk with directory descriptors; reject symlinks, including concurrent swaps."""
    pure = PurePosixPath(path)
    if (
        not isinstance(path, str)
        or not path
        or pure.is_absolute()
        or ".." in pure.parts
        or "\0" in path
    ):
        raise ValueError("path must be relative to workspace without '..'")
    parts = pure.parts
    current = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=current)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        if not parts:
            if not directory:
                raise ValueError("expected a file")
            return os.dup(current)
        descriptor = os.open(
            parts[-1],
            flags | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_DIRECTORY if directory else 0),
            0o600,
            dir_fd=current,
        )
        if not directory and not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("only regular files are supported")
        return descriptor
    finally:
        os.close(current)


def file_operation(request: dict[str, Any]) -> dict[str, Any]:
    action, path = request["operation"], request["path"]
    if action == "list":
        fd = open_path(path, directory=True)
        try:
            names = sorted(os.listdir(fd))
            return {
                "entries": [
                    {
                        "name": name,
                        "directory": stat.S_ISDIR(
                            os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
                        ),
                    }
                    for name in names[:200]
                ],
                "truncated": len(names) > 200,
            }
        finally:
            os.close(fd)
    if action == "write":
        data = request["text"].encode()
        if len(data) > 32768:
            raise ValueError("write limit is 32 KiB")
        fd = open_path(path, flags=os.O_WRONLY | os.O_CREAT, create=True)
        with os.fdopen(fd, "wb") as file:
            # Reject special files before truncate; writes are serialized by Runtime.
            file.truncate(0)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        return {"path": path, "size_bytes": len(data)}
    if action not in {"read", "artifact"}:
        raise ValueError("unknown file operation")
    limit = 16 * 1024**2 if action == "artifact" else 65536
    offset = request.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("invalid offset")
    with os.fdopen(open_path(path), "rb") as file:
        size = os.fstat(file.fileno()).st_size
        if action == "artifact" and size > limit:
            raise ValueError(
                "artifact exceeds 16 MiB; archive the workspace when ending environment"
            )
        file.seek(offset)
        data = file.read(limit)
    return {
        "path": path,
        "content_base64": base64.b64encode(data).decode(),
        "text": data.decode(errors="replace") if action == "read" else None,
        "next_offset": offset + len(data),
        "size_bytes": size,
        "eof": offset + len(data) >= size,
    }


class Job:
    def __init__(self, request: dict[str, Any]) -> None:
        self.request = request
        argv = request["argv"]
        timeout = request["timeout_seconds"]
        if (
            not isinstance(argv, list)
            or not 1 <= len(argv) <= 128
            or any(not isinstance(a, str) or "\0" in a for a in argv)
            or sum(len(a) for a in argv) > 16384
        ):
            raise ValueError("invalid argv (max 128 args / 16 KiB)")
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 86400
        ):
            raise ValueError("timeout must be 0–86400 seconds")
        fd = open_path(request["cwd"], directory=True)
        try:
            self.process = subprocess.Popen(
                argv,
                cwd=f"/proc/self/fd/{fd}",
                pass_fds=(fd,),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            os.close(fd)
        self.output = bytearray()
        self.truncated = False
        self.state = "running"
        self.exit_code: int | None = None
        self.stop_requested = threading.Event()
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()

    def kill(self) -> None:
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def watch(self) -> None:
        reason = "completed"
        deadline = time.monotonic() + self.request["timeout_seconds"]
        assert self.process.stdout is not None
        with self.process.stdout as stream, selectors.DefaultSelector() as selector:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            while True:
                if self.stop_requested.is_set() or time.monotonic() >= deadline:
                    reason = "cancelled" if self.stop_requested.is_set() else "timed_out"
                    self.kill()
                if self.process.poll() is not None:
                    # The main process may leave children holding pipes open.
                    self.kill()
                ready = selector.select(0.05)
                if ready:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        selector.unregister(stream)
                        if self.process.poll() is not None:
                            break
                        continue
                    remaining = LOG_LIMIT - len(self.output)
                    self.output.extend(chunk[:remaining])
                    self.truncated |= len(chunk) > remaining
                elif self.process.poll() is not None:
                    break
        self.exit_code = self.process.wait()
        self.kill()
        self.state = reason if reason != "completed" or self.exit_code == 0 else "failed"

    def status(self) -> dict[str, Any]:
        return {
            "job_id": self.request["job_id"],
            "state": self.state,
            "exit_code": self.exit_code,
            "logs_truncated": self.truncated,
        }


class Runtime:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            action = request["action"]
            if action == "health":
                return {"ready": True}
            if action == "file":
                return file_operation(request)
            job_id = request["job_id"]
            if action == "start":
                if job_id not in self.jobs:
                    if any(job.state == "running" for job in self.jobs.values()):
                        raise ValueError("environment busy; one active Job per environment")
                    # As PID 1, reap adopted children of completed Jobs. Their direct
                    # parents have already been waited by Job.watch; do not steal
                    # Popen exit statuses while a Job is active.
                    if os.getpid() == 1:
                        try:
                            while os.waitpid(-1, os.WNOHANG)[0]:
                                pass
                        except ChildProcessError:
                            pass
                    if len(self.jobs) >= 128:
                        raise ValueError("128 Job limit reached; create a new research environment")
                    self.jobs[job_id] = Job(request)
                elif self.jobs[job_id].request != request:
                    raise ValueError("job_id already has different parameters")
            job = self.jobs[job_id]
            if action == "stop":
                job.stop_requested.set()
                job.thread.join(5)
            if action == "logs":
                cursor = request.get("cursor", 0)
                if type(cursor) is not int or not 0 <= cursor <= len(job.output):
                    raise ValueError("invalid log cursor")
                chunk = bytes(job.output[cursor : cursor + 65536])
                return job.status() | {
                    "content_base64": base64.b64encode(chunk).decode(),
                    "text": chunk.decode(errors="replace"),
                    "next_cursor": cursor + len(chunk),
                }
            if action not in {"start", "status", "stop"}:
                raise ValueError("unknown action")
            return job.status()


def main() -> None:
    runtime = Runtime()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            try:
                line = self.rfile.readline(65537)
                if len(line) > 65536:
                    raise ValueError("request too large")
                result = runtime.dispatch(json.loads(line))
            except Exception as error:
                result = {"error": f"{type(error).__name__}: {error}"}
            self.wfile.write(json.dumps(result).encode() + b"\n")

    with socketserver.ThreadingUnixStreamServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.serve_forever()


if __name__ == "__main__":
    main()
