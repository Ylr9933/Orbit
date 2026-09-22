"""Linux ownership identity and durable journal helpers shared by supervisor/backend."""

import fcntl
import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked(path: Path, *, blocking: bool = True) -> Iterator[None]:
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield
    finally:
        os.close(fd)


def process_identity(pid: int) -> tuple[str, int, int] | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        # state (3), pgrp (5), starttime (22). Ignore zombies; they no longer execute.
        if fields[0] == "Z":
            return None
        return (fields[19], int(fields[2]), int(fields[3]))
    except FileNotFoundError:
        return None


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def group_members(group: int) -> tuple[tuple[int, str], ...]:
    found = []
    for path in Path("/proc").iterdir():
        if path.name.isdecimal() and int(path.name) != group:
            identity = process_identity(int(path.name))
            if identity and identity[1:] == (group, group):
                found.append((int(path.name), identity[0]))
    return tuple(found)


def signal_members(group: int, sig: signal.Signals) -> None:
    # pidfd binds a signal to a specific process; recheck starttime after opening it.
    for pid, start in group_members(group):
        try:
            descriptor = os.pidfd_open(pid)
            try:
                identity = process_identity(pid)
                if identity == (start, group, group):
                    signal.pidfd_send_signal(descriptor, sig)
            finally:
                os.close(descriptor)
        except ProcessLookupError:
            pass
