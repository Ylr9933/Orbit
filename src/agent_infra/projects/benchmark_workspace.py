"""Console-owned batch references and annotations, separate from execution evidence."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BenchmarkWorkspaceStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "workspace.sqlite3"

    def all(self, kind: str) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        with closing(sqlite3.connect(self.path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT key, body FROM entries WHERE kind=?", (kind,)).fetchall()
        return {key: json.loads(body) for key, body in rows}

    def save(self, kind: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(self.path, timeout=15)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS entries "
                "(kind TEXT, key TEXT, body TEXT, PRIMARY KEY(kind,key))"
            )
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT body FROM entries WHERE kind=? AND key=?", (kind, key)
            ).fetchone()
            current = json.loads(previous[0]) if previous else {}
            if body.get("revision", 0) != current.get("revision", 0):
                raise ValueError("内容已更新，请刷新后再保存")
            value = {
                **body,
                "revision": current.get("revision", 0) + 1,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            db.execute(
                "INSERT OR REPLACE INTO entries VALUES (?,?,?)", (kind, key, json.dumps(value))
            )
            db.commit()
        self.path.chmod(0o600)
        return value
