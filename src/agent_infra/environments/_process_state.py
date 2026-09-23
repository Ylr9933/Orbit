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
    except OSError:
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


def group_usage(group: int) -> tuple[float, int, int | None, int | None] | None:
    """Best-effort Linux process-group sample; never infer GPU usage from a host snapshot."""
    members = (group, *(pid for pid, _ in group_members(group)))
    clock = os.sysconf("SC_CLK_TCK")
    page = os.sysconf("SC_PAGE_SIZE")
    cpu_ticks, memory = 0, 0
    read_total, write_total = 0, 0
    observed = False
    io_observed = False
    for pid in members:
        try:
            if process_identity(pid) is None:
                continue
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if (int(fields[2]), int(fields[3])) != (group, group):
                continue
            cpu_ticks += int(fields[11]) + int(fields[12])
            memory += int(fields[21]) * page
            observed = True
            try:
                counters = dict(
                    line.split(": ", 1)
                    for line in Path(f"/proc/{pid}/io").read_text().splitlines()
                    if ": " in line
                )
                read_total += int(counters["read_bytes"])
                write_total += int(counters["write_bytes"])
                io_observed = True
            except (OSError, KeyError, ValueError):
                pass
        except (OSError, ValueError, IndexError):
            continue
    if not observed:
        return None
    return (
        cpu_ticks / clock,
        memory,
        read_total if io_observed else None,
        (write_total if io_observed else None),
    )


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
