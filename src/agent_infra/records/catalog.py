"""Mutable project catalog, separate from immutable execution evidence."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Protocol


class CatalogConflict(ValueError):
    """A concurrent edit changed the project revision."""


class ProjectCatalog(Protocol):
    def list_projects(self) -> list[dict[str, Any]]: ...

    def save(self, project: dict[str, Any], expected_revision: int) -> dict[str, Any]: ...


class LocalProjectCatalog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS projects "
                "(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,body TEXT NOT NULL)"
            )
            db.commit()
        path.chmod(0o600)

    def list_projects(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as db:
            return [
                json.loads(row[0]) for row in db.execute("SELECT body FROM projects ORDER BY id")
            ]

    def save(self, project: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision FROM projects WHERE id=?", (project["id"],)
            ).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise CatalogConflict("项目已被修改，请刷新后重试")
            saved = project | {"revision": expected_revision + 1}
            db.execute(
                "INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "revision=excluded.revision,body=excluded.body",
                (saved["id"], saved["revision"], json.dumps(saved, ensure_ascii=False)),
            )
            db.commit()
        return saved
