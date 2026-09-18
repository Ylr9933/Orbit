"""Local Project metadata. Read operations do not create state."""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from agent_infra.projects._filesystem import absolute, directory
from agent_infra.projects.api import (
    InitializationStatus,
    Project,
    ProjectConflict,
    ProjectError,
    ProjectNotFound,
    ProjectStatus,
)


@dataclass(frozen=True)
class StoredProject:
    project: Project
    snapshot: dict[str, str]
    directories: tuple[str, ...]
    request: dict[str, str]


def _decode(row: sqlite3.Row) -> StoredProject:
    return StoredProject(
        Project.from_dict(json.loads(row["body"])),
        json.loads(row["snapshot"]),
        tuple(json.loads(row["directories"])),
        json.loads(row["request"]),
    )


class LocalProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = absolute(root)
        self.path = self.root / "projects.sqlite3"

    @contextmanager
    def writer(self) -> Iterator[None]:
        with directory(self.root, create=True) as parent:
            fd = os.open(
                "writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent
            )
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ProjectError("invalid project store lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    @contextmanager
    def _connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with directory(self.root) as parent:
            if write:
                fd = os.open(
                    "projects.sqlite3", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent
                )
                os.close(fd)
            info = os.stat("projects.sqlite3", dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ProjectError("project store must be a private regular file")
            path = Path(f"/proc/self/fd/{parent}/projects.sqlite3")
            db = sqlite3.connect(
                path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=30
            )
            db.row_factory = sqlite3.Row
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}:
                    raise ProjectError("unsupported project store version")
                if write:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS projects ("
                        "id TEXT PRIMARY KEY, operation TEXT NOT NULL UNIQUE, "
                        "workspace TEXT NOT NULL UNIQUE, body TEXT NOT NULL, "
                        "snapshot TEXT NOT NULL, directories TEXT NOT NULL, "
                        "request TEXT NOT NULL)"
                    )
                    db.execute("PRAGMA user_version=1")
                elif version == 0:
                    if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        raise ProjectError("unrecognized project store schema")
                    # A crash before the very first transaction committed leaves an empty DB.
                    raise FileNotFoundError("project store initialization has not committed")
                yield db
                if write:
                    db.commit()
            finally:
                db.close()

    def find(
        self, *, operation: str | None = None, workspace: str | None = None
    ) -> StoredProject | None:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT * FROM projects WHERE operation=? OR workspace=?",
                    (operation, workspace),
                ).fetchall()
                if len(row) > 1:
                    raise ProjectConflict("operation and destination identify different projects")
                return _decode(row[0]) if row else None
        except FileNotFoundError:
            return None

    def get(self, project_id: str) -> StoredProject:
        try:
            with self._connect() as db:
                row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
                if row:
                    return _decode(row)
        except FileNotFoundError:
            pass
        raise ProjectNotFound(f"project not found: {project_id}")

    def list_projects(self) -> tuple[Project, ...]:
        try:
            with self._connect() as db:
                return tuple(
                    _decode(row).project for row in db.execute("SELECT * FROM projects ORDER BY id")
                )
        except FileNotFoundError:
            return ()

    def reserve(self, item: StoredProject) -> None:
        p = item.project
        try:
            with self._connect(write=True) as db:
                db.execute(
                    "INSERT INTO projects VALUES (?,?,?,?,?,?,?)",
                    (
                        p.project_id,
                        p.operation_id,
                        p.workspace,
                        json.dumps(p.to_dict()),
                        json.dumps(item.snapshot),
                        json.dumps(item.directories),
                        json.dumps(item.request),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ProjectConflict("operation or destination is already registered") from error

    def mark_ready(self, project_id: str, manifest: str) -> Project:
        with self._connect(write=True) as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ProjectNotFound(project_id)
            item = _decode(row)
            p = replace(item.project, initialization=InitializationStatus.READY)
            db.execute(
                "UPDATE projects SET body=?, snapshot=? WHERE id=?",
                (
                    json.dumps(p.to_dict()),
                    json.dumps(item.snapshot | {"project.yaml": manifest}),
                    project_id,
                ),
            )
            return p

    def update(
        self,
        project_id: str,
        *,
        expected_revision: int,
        title: str | None = None,
        status: ProjectStatus | None = None,
    ) -> Project:
        """CAS metadata update; recover materializes the guarded manifest projection."""
        with self.writer(), self._connect(write=True) as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ProjectNotFound(project_id)
            p = _decode(row).project
            if type(expected_revision) is not int or p.revision != expected_revision:
                raise ProjectConflict("project revision changed; reload before updating")
            if p.initialization != InitializationStatus.READY:
                raise ProjectConflict("recover pending initialization/projection before updating")
            updated = replace(
                p,
                title=p.title if title is None else title,
                status=p.status if status is None else status,
                revision=p.revision + 1,
                updated_at=datetime.now(UTC).isoformat(),
                initialization=InitializationStatus.PROJECTION_PENDING,
            )
            db.execute(
                "UPDATE projects SET body=? WHERE id=?", (json.dumps(updated.to_dict()), project_id)
            )
            return updated
