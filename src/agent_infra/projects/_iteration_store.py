"""Iteration documents share Projects transactions and its cross-process writer lock."""

import json
from typing import Any

from agent_infra.projects._database import ProjectDatabase


class IterationStore:
    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def get(self, project: str, kind: str, key: str) -> dict[str, Any]:
        with self.database.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < 4:
                raise KeyError(key)
            row = db.execute(
                "SELECT body FROM iteration_documents WHERE project_id=? AND kind=? AND id=?",
                (project, kind, key),
            ).fetchone()
        if row is None:
            raise KeyError(key)
        return dict(json.loads(row[0]))

    def list(self, project: str, kind: str, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be 1–100")
        with self.database.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < 4:
                return []
            rows = db.execute(
                "SELECT body FROM iteration_documents WHERE project_id=? AND kind=? "
                "ORDER BY rowid DESC LIMIT ?",
                (project, kind, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, project: str, kind: str, key: str, body: dict[str, Any]) -> None:
        """Caller must hold database.writer across read/modify/write and side-effect receipts."""
        with self.database.connect(write=True) as db:
            db.execute(
                "INSERT INTO iteration_documents VALUES (?,?,?,?) "
                "ON CONFLICT(project_id,kind,id) DO UPDATE SET body=excluded.body",
                (project, kind, key, json.dumps(body, allow_nan=False)),
            )
