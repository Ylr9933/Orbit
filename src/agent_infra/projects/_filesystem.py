"""Linux local filesystem primitives; no-clobber publication and pinned directories."""

import ctypes
import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_infra.projects.api import ProjectConflict, ProjectError

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def absolute(path: Path) -> Path:
    if ".." in path.parts:
        raise ProjectError("parent traversal (..) is not allowed in project paths")
    return Path(os.path.abspath(path.expanduser()))


@contextmanager
def directory(path: Path, *, create: bool = False) -> Iterator[int]:
    """Walk without following symlinks; keep the final inode pinned until exit."""
    path = absolute(path)
    fd = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def exists(parent: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def read_file(parent: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProjectConflict(f"not a private regular file: {name}")
        if info.st_size > 2 * 1024 * 1024:
            raise ProjectConflict(f"generated file exceeds size limit: {name}")
        return stream.read(2 * 1024 * 1024 + 1)


def write_file(parent: int, name: str, content: bytes, *, replace: bool = False) -> None:
    """Write via an owned scratch file. Default publication cannot replace another file."""
    scratch = f".{name}.init-tmp"
    fd = os.open(
        scratch, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent
    )
    with os.fdopen(fd, "wb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProjectConflict(f"invalid initialization scratch file: {scratch}")
        stream.truncate(0)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(scratch, name, src_dir_fd=parent, dst_dir_fd=parent)
    else:
        os.link(scratch, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(scratch, dir_fd=parent)
    os.fsync(parent)


def publish(parent: int, stage: str, destination: str) -> None:
    """Linux renameat2 avoids the empty-directory overwrite possible with os.rename."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as error:
        raise ProjectError("atomic project publication requires Linux renameat2") from error
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(stage), parent, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ProjectConflict("destination already exists; nothing was overwritten")
        raise OSError(code, os.strerror(code))
    os.fsync(parent)


@contextmanager
def child_directory(parent: int, name: str, *, create: bool = False) -> Iterator[int]:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def populate(parent: int, files: dict[str, str], directories: tuple[str, ...]) -> None:
    """Fill only missing files and verify existing ones; keep edits for manual recovery."""
    entries = {path.split("/", 1)[0] for path in (*files, *directories)}
    scratch_names = {f".{name}.init-tmp" for name in files if "/" not in name}
    unexpected = set(os.listdir(parent)) - entries - scratch_names
    if unexpected:
        raise ProjectConflict(f"unrecognized staging entries: {sorted(unexpected)}")
    for name in sorted(entries):
        if name in files:
            expected = files[name].encode("utf-8")
            if exists(parent, name):
                scratch = f".{name}.init-tmp"
                if exists(parent, scratch):
                    target_info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    scratch_info = os.stat(scratch, dir_fd=parent, follow_symlinks=False)
                    if (target_info.st_dev, target_info.st_ino) == (
                        scratch_info.st_dev,
                        scratch_info.st_ino,
                    ) and stat.S_ISREG(target_info.st_mode):
                        # A crash between link() and unlink() leaves two names for our file.
                        os.unlink(scratch, dir_fd=parent)
                if read_file(parent, name) != expected:
                    raise ProjectConflict(
                        f"generated file was modified: {name}; preserve and inspect"
                    )
                if exists(parent, scratch):
                    read_file(parent, scratch)  # Reject links before removing owned scratch.
                    os.unlink(scratch, dir_fd=parent)
            else:
                write_file(parent, name, expected)
        else:
            with child_directory(parent, name, create=True) as child:
                prefix = name + "/"
                populate(
                    child,
                    {p[len(prefix) :]: text for p, text in files.items() if p.startswith(prefix)},
                    tuple(p[len(prefix) :] for p in directories if p.startswith(prefix)),
                )
    os.fsync(parent)


def verify(parent: int, files: dict[str, str], directories: tuple[str, ...]) -> None:
    """Published pending workspaces must match the reserved snapshot exactly."""
    entries = {p.split("/", 1)[0] for p in (*files, *directories)}
    if set(os.listdir(parent)) != entries:
        raise ProjectConflict("pending workspace differs from initialization snapshot")
    for name in entries:
        if name in files:
            if read_file(parent, name) != files[name].encode("utf-8"):
                raise ProjectConflict(f"pending workspace file was modified: {name}")
        else:
            with child_directory(parent, name) as child:
                prefix = name + "/"
                verify(
                    child,
                    {p[len(prefix) :]: v for p, v in files.items() if p.startswith(prefix)},
                    tuple(p[len(prefix) :] for p in directories if p.startswith(prefix)),
                )
