"""Shared regular-file traversal and content fingerprints; no module backends."""

import hashlib
import json
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
