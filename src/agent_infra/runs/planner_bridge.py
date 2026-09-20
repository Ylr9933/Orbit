"""Bounded file transport for one untrusted Planner; all business rules stay in Projects."""

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any


class PlannerBridge:
    def __init__(
        self, workspace: Path, call: Callable[[str, dict[str, Any]], dict[str, Any]]
    ) -> None:
        self.workspace, self.call = workspace, call
        self.previous: bytes | None = None

    def poll(self) -> dict[str, Any] | None:
        root = os.open(self.workspace, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fd = os.open(
                    "request.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
                )
            except FileNotFoundError:
                return None
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 60000:
                    raise ValueError(
                        "Planner request must be a single regular file up to 60000 bytes"
                    )
                raw = os.read(fd, 60001)
            finally:
                os.close(fd)
            if raw == self.previous:
                return None
            request = json.loads(raw)
            key = request.get("id")
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise ValueError("invalid Planner message ID")
            try:
                if not isinstance(request.get("options", {}), dict):
                    raise ValueError("options must be an object")
                result = self.call(request["action"], request.get("options", {}))
                response = {"id": key, "result": result}
                encoded = json.dumps(response, ensure_ascii=False, default=str).encode()
                if len(encoded) > 2 * 1024**2:
                    raise ValueError("response exceeds Planner transport limit")
            except (ValueError, KeyError, TypeError) as error:
                response = {"id": key, "error": type(error).__name__, "message": str(error)}
                encoded = json.dumps(response).encode()
            # Never follow a container-created response symlink or special file.
            name = ".response-" + os.urandom(12).hex()
            fd = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root
            )
            try:
                with os.fdopen(fd, "wb") as file:
                    file.write(encoded)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(name, "response.json", src_dir_fd=root, dst_dir_fd=root)
            finally:
                try:
                    os.unlink(name, dir_fd=root)
                except FileNotFoundError:
                    pass
            self.previous = raw
            return {"request": request, "response": response}
        finally:
            os.close(root)
