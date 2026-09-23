"""Shared regular-file traversal and content fingerprints; no module backends."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in value:
        raise ValueError("material path must be a non-empty relative path without traversal")
    return path


def resolve_material(root: Path, source: str) -> Path:
    relative = relative_path(source)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("material symlinks are not supported")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("material path escapes root")
    return current


def content_digest(path: Path) -> str:
    digest = hashlib.sha256()

    def visit(item: Path, name: str) -> None:
        if item.is_symlink():
            raise ValueError("material symlinks are not supported")
        if item.is_file():
            digest.update(json.dumps(["file", name], ensure_ascii=False).encode())
            file_digest = hashlib.sha256()
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            digest.update(file_digest.digest())
        elif item.is_dir():
            digest.update(json.dumps(["directory", name], ensure_ascii=False).encode())
            for child in sorted(item.iterdir()):
                visit(child, f"{name}/{child.name}")
        else:
            raise ValueError("material is missing or is not a regular file/directory")

    visit(path, ".")
    return "sha256:" + digest.hexdigest()


def resume_copy_file(source: Path, destination: Path) -> None:
    """Resume a private regular-file copy and verify the full result before publication."""
    if source.is_symlink() or not source.is_file() or destination.is_symlink():
        raise ValueError("resumable copy requires regular files without symlinks")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists() and not destination.is_file():
        raise ValueError("resumable destination is not a regular file")
    size = source.stat().st_size
    copied = destination.stat().st_size if destination.exists() else 0
    if copied > size:
        raise ValueError("resumable destination is larger than its source")
    source_hash = hashlib.sha256()
    descriptor = os.open(destination, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with source.open("rb") as original, os.fdopen(descriptor, "r+b") as target:
        target.seek(0)
        remaining = copied
        while remaining:
            left = original.read(min(1024 * 1024, remaining))
            right = target.read(len(left))
            if not left or left != right:
                raise ValueError("resumable destination differs from frozen source")
            source_hash.update(left)
            remaining -= len(left)
        target.seek(copied)
        for chunk in iter(lambda: original.read(1024 * 1024), b""):
            target.write(chunk)
            source_hash.update(chunk)
        target.flush()
        os.fsync(target.fileno())
    with destination.open("rb") as copied_file:
        actual = hashlib.sha256()
        for chunk in iter(lambda: copied_file.read(1024 * 1024), b""):
            actual.update(chunk)
    if source_hash.digest() != actual.digest() or destination.stat().st_size != size:
        raise ValueError("resumable copy integrity check failed")
