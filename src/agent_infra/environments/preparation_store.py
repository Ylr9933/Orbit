"""Private local environment catalog. Controller serializes writes; readers use snapshots."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class EnvironmentCatalog:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root
        self.path = root / "environments.sqlite3"
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported environment catalog version")
            db.execute(
                "CREATE TABLE IF NOT EXISTS plans "
                "(id TEXT PRIMARY KEY, project TEXT NOT NULL, document TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            db.execute("PRAGMA user_version=1")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA synchronous=FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, plan: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO plans VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                (plan["plan_id"], plan["project_id"], json.dumps(plan)),
            )

    def get(self, project: str, identifier: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT document FROM plans WHERE id=? AND project=?", (identifier, project)
            ).fetchone()
        if row is None:
            raise KeyError("environment plan not found in bound project")
        return dict(json.loads(row[0]))

    def list(self, project: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT document FROM plans" + (" WHERE project=?" if project else ""),
                (project,) if project else (),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def cached(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT document FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, value: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(value)))
