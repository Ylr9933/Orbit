"""Durable project bindings, Job intents and idempotent research operations.

Run state stays in RunControlStore; execution evidence stays in Records.
"""

import hashlib
import json
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from agent_infra.runs.control_api import ControlError


class ResearchStore:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "research.sqlite3"
        self.root = root
        with closing(self.connect()) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported research control schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS bindings (
                    token TEXT PRIMARY KEY, project TEXT NOT NULL, session TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, run TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT);
                PRAGMA user_version=1;
            """)
        self.path.chmod(0o600)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def bind(self, project: str, session: str) -> str:
        token = secrets.token_urlsafe(32)
        with closing(self.connect()) as db:
            db.execute(
                "INSERT INTO bindings VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), project, session),
            )
            db.commit()
        return token

    def binding(self, token: str) -> tuple[str, str]:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT project,session FROM bindings WHERE token=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        if row is None:
            raise ControlError("invalid_binding", "create a project-scoped research binding")
        return str(row[0]), str(row[1])

    def begin(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        encoded = json.dumps(payload, sort_keys=True)
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload,result FROM operations WHERE key=?", (key,)).fetchone()
            if row:
                if row[0] != encoded:
                    raise ControlError(
                        "idempotency_conflict", "operation ID has different parameters"
                    )
                if row[1] is None:
                    raise ControlError(
                        "operation_uncertain",
                        "operation interrupted; inspect context/run/jobs before issuing a new ID",
                    )
                return dict(json.loads(row[1]))
            db.execute("INSERT INTO operations VALUES (?,?,NULL)", (key, encoded))
            db.commit()
        return None

    def finish(self, key: str, result: dict[str, Any]) -> None:
        with closing(self.connect()) as db:
            db.execute("UPDATE operations SET result=? WHERE key=?", (json.dumps(result), key))
            db.commit()

    def save_job(self, job: dict[str, Any]) -> None:
        with closing(self.connect()) as db:
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                (job["job_id"], job["run_id"], json.dumps(job)),
            )
            db.commit()

    def jobs(self, run_id: str) -> list[dict[str, Any]]:
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT document FROM jobs WHERE run=? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def job(self, run_id: str, job_id: str) -> dict[str, Any]:
        return (
            next((j for j in self.jobs(run_id) if j["job_id"] == job_id), None) or self._missing()
        )

    @staticmethod
    def _missing() -> Any:
        raise KeyError("job not found in this research Run")

    def pending_jobs(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT document FROM jobs WHERE json_extract(document, '$.log_finalized') IS NOT 1"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
