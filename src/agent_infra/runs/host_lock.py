"""One local administrator controller per OS account, across all state directories."""

import fcntl
import json
import os
from pathlib import Path
from typing import IO


class HostControllerLock:
    def __init__(self, state: Path, *, namespace: Path | None = None) -> None:
        self.state = str(state.resolve())
        # Never derive the production namespace from --state-dir or the working directory.
        root = namespace or Path(f"/tmp/agent-infra-controller-{os.getuid()}")
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise ValueError("controller lock directory must be private and owned by this user")
        fd = os.open(root / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.file: IO[str] = os.fdopen(fd, "r+")
        self.marker = root / "owner.json"
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            previous = self.marker.read_text() if self.marker.exists() else ""
            if previous:
                marker = json.loads(previous)
                if marker["dirty"] and marker["state"] != self.state:
                    raise RuntimeError(
                        "previous controller needs recovery: restart with "
                        f"--state-dir {marker['state']}"
                    )
            self._write(True)
        except BaseException:
            self.file.close()
            raise

    def _write(self, dirty: bool) -> None:
        temporary = self.marker.with_suffix(".tmp")
        with temporary.open("w") as file:
            json.dump({"state": self.state, "dirty": dirty}, file)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(self.marker)
        descriptor = os.open(self.marker.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def close(self, *, clean: bool) -> None:
        if not self.file.closed:
            if clean:
                self._write(False)
            self.file.close()
