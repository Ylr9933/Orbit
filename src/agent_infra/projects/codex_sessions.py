"""Persistent explicit ownership and replay cursor for interactive Codex sessions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from agent_infra.projects.api import ProjectConflict
from agent_infra.projects.local import LocalProjectStore


@dataclass(frozen=True)
class CodexBinding:
    thread_id: str
    project_id: str
    started_at: str
    cwd: str
    next_offset: int
    next_line: int


class CodexBindingStore:
    def __init__(self, projects: LocalProjectStore) -> None:
        self.projects = projects

    def get(self, thread_id: str) -> CodexBinding | None:
        try:
            with self.projects.database.connect() as db:
                row = db.execute(
                    "SELECT * FROM codex_sessions WHERE thread_id=?", (thread_id,)
                ).fetchone()
                return CodexBinding(**dict(row)) if row is not None else None
        except FileNotFoundError:
            return None
        except sqlite3.OperationalError as error:
            if "no such table: codex_sessions" in str(error):
                return None
            raise

    def bind(self, thread_id: str, project_id: str, started_at: str, cwd: str) -> CodexBinding:
        with self.projects.database.writer(), self.projects.database.connect(write=True) as db:
            row = db.execute(
                "SELECT * FROM codex_sessions WHERE thread_id=?", (thread_id,)
            ).fetchone()
            if row is not None:
                binding = CodexBinding(**dict(row))
                if (binding.project_id, binding.started_at, binding.cwd) != (
                    project_id,
                    started_at,
                    cwd,
                ):
                    raise ProjectConflict(
                        "Codex session is already bound to another project or metadata"
                    )
                return binding
            db.execute(
                "INSERT INTO codex_sessions(thread_id,project_id,started_at,cwd) VALUES (?,?,?,?)",
                (thread_id, project_id, started_at, cwd),
            )
            return CodexBinding(thread_id, project_id, started_at, cwd, 0, 0)

    def advance(
        self, thread_id: str, expected_offset: int, next_offset: int, next_line: int
    ) -> None:
        with self.projects.database.writer(), self.projects.database.connect(write=True) as db:
            updated = db.execute(
                "UPDATE codex_sessions SET next_offset=?,next_line=? "
                "WHERE thread_id=? AND next_offset=?",
                (next_offset, next_line, thread_id, expected_offset),
            )
            if updated.rowcount != 1:
                raise ProjectConflict("Codex capture cursor changed; retry synchronization")
