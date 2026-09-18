"""Immutable experiment/task associations in the shared control database."""

import json

from agent_infra.projects._database import ProjectDatabase
from agent_infra.projects.api import ProjectConflict, ProjectNotFound
from agent_infra.projects.compilation_api import CompiledExperiment


class CompilationStore:
    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def save(self, item: CompiledExperiment) -> None:
        """Caller owns the shared writer lock; bundle publication precedes this commit."""
        with self.database.connect(write=True) as db:
            encoded = json.dumps(item.to_dict(), sort_keys=True)
            old = db.execute(
                "SELECT body FROM compiled_tasks WHERE task_id=? AND revision=?",
                (item.task.task_id, item.task.revision),
            ).fetchone()
            if old:
                if old["body"] != encoded:
                    raise ProjectConflict("compiled task identity already has different content")
                return
            db.execute(
                "INSERT INTO compiled_tasks VALUES (?,?,?,?,?)",
                (
                    item.project_id,
                    item.experiment_id,
                    item.task.task_id,
                    item.task.revision,
                    encoded,
                ),
            )

    def get(self, task_id: str, revision: str) -> CompiledExperiment:
        with self.database.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] >= 3:
                row = db.execute(
                    "SELECT body FROM compiled_tasks WHERE task_id=? AND revision=?",
                    (task_id, revision),
                ).fetchone()
                if row:
                    return CompiledExperiment.from_dict(json.loads(row["body"]))
        raise ProjectNotFound("compiled task association not found")

    def list(
        self, project_id: str, *, limit: int = 20, offset: int = 0
    ) -> list[CompiledExperiment]:
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError("limit must be 1–100 and offset a nonnegative integer")
        with self.database.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                return []
            rows = db.execute(
                "SELECT body FROM compiled_tasks WHERE project_id=? "
                "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            )
            return [CompiledExperiment.from_dict(json.loads(row["body"])) for row in rows]
