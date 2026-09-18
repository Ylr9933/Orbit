"""Local Project metadata. Read operations do not create state."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_infra.projects._filesystem import absolute, directory
from agent_infra.projects.api import (
    InitializationStatus,
    Project,
    ProjectConflict,
    ProjectError,
    ProjectNotFound,
    ProjectStatus,
    require_text,
)
from agent_infra.projects.research_api import ResearchDraft, ResearchRevision


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
                if version not in {0, 1, 2}:
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
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS research_revisions ("
                        "project_id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, "
                        "reason TEXT NOT NULL, created_at TEXT NOT NULL, "
                        "PRIMARY KEY(project_id, revision))"
                    )
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS research_heads ("
                        "project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                        "accepted_revision INTEGER, published TEXT NOT NULL, pending TEXT)"
                    )
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS research_confirmations ("
                        "project_id TEXT NOT NULL, revision INTEGER NOT NULL, "
                        "digest TEXT NOT NULL, "
                        "decision TEXT NOT NULL, created_at TEXT NOT NULL, "
                        "PRIMARY KEY(project_id, revision))"
                    )
                    db.execute("PRAGMA user_version=2")
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

    @staticmethod
    def _research_row(row: sqlite3.Row) -> ResearchRevision:
        return ResearchRevision(
            row["project_id"],
            row["revision"],
            ResearchDraft(row["body"]),
            row["reason"],
            row["created_at"],
        )

    def research_state(self, project_id: str) -> dict[str, Any]:
        """Consistent read of latest draft, chosen revision and projection recovery state."""
        self.get(project_id)
        with self._connect() as db:
            db.execute("BEGIN")
            empty: dict[str, Any] = {
                "latest": None,
                "accepted": None,
                "confirmation": None,
                "published": {},
                "pending": None,
            }
            if db.execute("PRAGMA user_version").fetchone()[0] < 2:
                return empty
            head = db.execute(
                "SELECT * FROM research_heads WHERE project_id=?", (project_id,)
            ).fetchone()
            if head is None:
                return empty

            def revision(number: int) -> ResearchRevision:
                row = db.execute(
                    "SELECT * FROM research_revisions WHERE project_id=? AND revision=?",
                    (project_id, number),
                ).fetchone()
                if row is None:
                    raise ProjectError("research head refers to a missing revision")
                return self._research_row(row)

            chosen = head["accepted_revision"]
            confirmation = db.execute(
                "SELECT * FROM research_confirmations WHERE project_id=? AND revision=?",
                (project_id, chosen),
            ).fetchone()
            return {
                "latest": revision(head["revision"]),
                "accepted": revision(chosen) if chosen is not None else None,
                "confirmation": dict(confirmation) if confirmation else None,
                "published": json.loads(head["published"]),
                "pending": json.loads(head["pending"]) if head["pending"] else None,
            }

    def research_revision(self, project_id: str, revision: int) -> ResearchRevision:
        self.get(project_id)
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] >= 2:
                row = db.execute(
                    "SELECT * FROM research_revisions WHERE project_id=? AND revision=?",
                    (project_id, revision),
                ).fetchone()
                if row:
                    return self._research_row(row)
        raise ProjectNotFound(f"research revision not found: {revision}")

    def research_history(
        self, project_id: str, *, limit: int = 20, before: int | None = None
    ) -> list[dict[str, Any]]:
        self.get(project_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("history limit must be between 1 and 100")
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < 2:
                return []
            rows = db.execute(
                "SELECT r.*, c.decision AS confirmed_decision, c.created_at AS confirmed_at "
                "FROM research_revisions r LEFT JOIN research_confirmations c "
                "ON r.project_id=c.project_id AND r.revision=c.revision "
                "WHERE r.project_id=? AND r.revision<? ORDER BY r.revision DESC LIMIT ?",
                (project_id, before or 2**63 - 1, limit),
            )
            return [
                {
                    "revision": row["revision"],
                    "digest": self._research_row(row).draft.digest,
                    "reason": row["reason"],
                    "created_at": row["created_at"],
                    "confirmation": (
                        {"decision": row["confirmed_decision"], "created_at": row["confirmed_at"]}
                        if row["confirmed_decision"] is not None
                        else None
                    ),
                }
                for row in rows
            ]

    def save_research(
        self,
        project_id: str,
        draft: ResearchDraft,
        *,
        expected_revision: int,
        reason: str,
        files: dict[str, str],
        imported: dict[str, str] | None = None,
    ) -> ResearchRevision:
        """Called under writer(); commit document and desired projection together."""
        require_text(reason, "reason", 2000)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ProjectError("expected_revision must be a non-negative integer")
        with self._connect(write=True) as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ProjectNotFound(project_id)
            project = _decode(row)
            if project.project.initialization != InitializationStatus.READY:
                raise ProjectConflict("recover project initialization before planning")
            head = db.execute(
                "SELECT * FROM research_heads WHERE project_id=?", (project_id,)
            ).fetchone()
            current = head["revision"] if head else 0
            if current:
                saved = self._research_row(
                    db.execute(
                        "SELECT * FROM research_revisions WHERE project_id=? AND revision=?",
                        (project_id, current),
                    ).fetchone()
                )
                if (
                    current in {expected_revision, expected_revision + 1}
                    and saved.draft == draft
                    and saved.reason == reason
                ):
                    return saved  # Retrying after a committed save never creates another revision.
            if current != expected_revision:
                raise ProjectConflict("research revision changed; reload context before saving")
            created = datetime.now(UTC).isoformat()
            revision = ResearchRevision(project_id, current + 1, draft, reason, created)
            db.execute(
                "INSERT INTO research_revisions VALUES (?,?,?,?,?)",
                (project_id, revision.revision, draft.content_json, reason, created),
            )
            baseline = (
                json.loads(head["published"])
                if head
                else {
                    path: [hashlib.sha256(project.snapshot[path].encode()).hexdigest()]
                    for path in files
                }
            )
            for path, text in [*files.items(), *(imported or {}).items()]:
                digest = hashlib.sha256(text.encode()).hexdigest()
                if digest not in baseline[path]:
                    baseline[path].append(digest)
            if head is None:
                db.execute(
                    "INSERT INTO research_heads VALUES (?,?,NULL,?,?)",
                    (project_id, revision.revision, json.dumps(baseline), json.dumps(files)),
                )
            else:
                db.execute(
                    "UPDATE research_heads SET revision=?, published=?, pending=? "
                    "WHERE project_id=?",
                    (revision.revision, json.dumps(baseline), json.dumps(files), project_id),
                )
            return revision

    def finish_research_export(self, project_id: str, revision: int) -> None:
        """Called under writer(), after all desired files have been verified or published."""
        with self._connect(write=True) as db:
            cursor = db.execute(
                "UPDATE research_heads SET pending=NULL "
                "WHERE project_id=? AND revision=? AND pending IS NOT NULL",
                (project_id, revision),
            )
            if cursor.rowcount != 1:
                raise ProjectConflict("research projection changed; reload before exporting")

    def confirm_research(
        self, project_id: str, *, revision: int, digest: str, decision: str
    ) -> dict[str, Any]:
        """Record the caller's decision for the exact current draft, without executing it."""
        require_text(decision, "decision", 4000)
        with self._connect(write=True) as db:
            head = db.execute(
                "SELECT * FROM research_heads WHERE project_id=?", (project_id,)
            ).fetchone()
            if head is None or type(revision) is not int or head["revision"] != revision:
                raise ProjectConflict("confirmation is stale; review the current research revision")
            saved = self._research_row(
                db.execute(
                    "SELECT * FROM research_revisions WHERE project_id=? AND revision=?",
                    (project_id, revision),
                ).fetchone()
            )
            if saved.draft.digest != digest:
                raise ProjectConflict("confirmation digest does not match the research revision")
            previous = db.execute(
                "SELECT * FROM research_confirmations WHERE project_id=? AND revision=?",
                (project_id, revision),
            ).fetchone()
            if previous:
                if previous["decision"] != decision:
                    raise ProjectConflict("this revision already has a different recorded decision")
                return dict(previous)
            created = datetime.now(UTC).isoformat()
            db.execute(
                "INSERT INTO research_confirmations VALUES (?,?,?,?,?)",
                (project_id, revision, digest, decision, created),
            )
            db.execute(
                "UPDATE research_heads SET accepted_revision=? WHERE project_id=?",
                (revision, project_id),
            )
            return {
                "project_id": project_id,
                "revision": revision,
                "digest": digest,
                "decision": decision,
                "created_at": created,
            }
