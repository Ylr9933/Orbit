"""Bounded copying of explicitly selected materials; never links live project files."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agent_infra.contracts.files import relative_path
from agent_infra.projects import _filesystem as fs
from agent_infra.projects.api import ProjectConflict, ProjectError


@dataclass
class CopyBudget:
    remaining_bytes: int
    remaining_entries: int = 10_000


def copy_material(root: Path, source: str, target: Path, budget: CopyBudget) -> None:
    """Reject symlinks/special files and detect ordinary concurrent edits while streaming."""
    relative = relative_path(source)
    with fs.directory(root / str(relative.parent)) as parent:
        _copy(parent, relative.name, target, budget, depth=0)


def _copy(parent: int, name: str, target: Path, budget: CopyBudget, *, depth: int) -> None:
    budget.remaining_entries -= 1
    if budget.remaining_entries < 0 or depth > 64:
        raise ProjectError("material entry/depth limit exceeded; select a smaller input")
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISDIR(before.st_mode):
        with fs.child_directory(parent, name) as child:
            target.mkdir(mode=0o700, parents=True)
            entries = sorted(os.listdir(child))
            for entry in entries:
                _copy(child, entry, target / entry, budget, depth=depth + 1)
            if sorted(os.listdir(child)) != entries:
                raise ProjectConflict("material directory changed during copy")
            with fs.directory(target) as copied_directory:
                os.fsync(copied_directory)
    elif stat.S_ISREG(before.st_mode) and before.st_nlink == 1:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as src:
            opened = os.fstat(src.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ProjectConflict("material file changed during copy")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as dst:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    budget.remaining_bytes -= len(chunk)
                    if budget.remaining_bytes < 0:
                        raise ProjectError(
                            "material byte budget exceeded; raise the limit explicitly"
                        )
                    dst.write(chunk)
                dst.flush()
                os.fchmod(dst.fileno(), 0o700 if before.st_mode & 0o111 else 0o600)
                os.fsync(dst.fileno())
    else:
        raise ProjectError(
            "materials must be regular files/directories without symlinks or hardlinks"
        )
    after = os.stat(name, dir_fd=parent, follow_symlinks=False)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise ProjectConflict("material changed during copy; retry after writers finish")
