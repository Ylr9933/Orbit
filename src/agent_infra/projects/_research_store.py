"""Research snapshot and confirmation queries, using the shared Project database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent_infra.projects.api import (
    InitializationStatus,
    Project,
    ProjectConflict,
    ProjectError,
    ProjectNotFound,
    require_text,
)
from agent_infra.projects.research_api import ResearchDraft, ResearchRevision

if TYPE_CHECKING:
    from agent_infra.projects.local import LocalProjectStore


class ResearchStore:
    def __init__(self, store: LocalProjectStore) -> None:
        self.store = store
        self.database = store.database

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
        self.store.get(project_id)
        with self.database.connect() as db:
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
        self.store.get(project_id)
        with self.database.connect() as db:
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
        self.store.get(project_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("history limit must be between 1 and 100")
        with self.database.connect() as db:
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
        with self.database.connect(write=True) as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ProjectNotFound(project_id)
            project = Project.from_dict(json.loads(row["body"]))
            if project.initialization != InitializationStatus.READY:
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
                    path: [hashlib.sha256(json.loads(row["snapshot"])[path].encode()).hexdigest()]
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
        with self.database.connect(write=True) as db:
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
        with self.database.connect(write=True) as db:
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
