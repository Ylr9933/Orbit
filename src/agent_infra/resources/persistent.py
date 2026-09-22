"""SQLite-backed low-concurrency leases for recoverable benchmark execution."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from agent_infra.resources.api import (
    AllocationStatus,
    LeaseCapacity,
    PersistentLeaseDecision,
    PersistentLeaseState,
    PersistentResourceLease,
    ResourceClaim,
    ResourceShortage,
)


def _now() -> datetime:
    return datetime.now(UTC)


class PersistentLeaseStore:
    """Idempotent claims with fencing epochs and retained release history.

    BM05-A intentionally defaults to one active lease. Numeric limits are enforced only when an
    operator supplies them; otherwise the ledger claims exclusive-slot admission, not cgroups.
    """

    def __init__(self, root: Path, capacity: LeaseCapacity | None = None) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "leases.sqlite3"
        self.capacity = capacity or LeaseCapacity()
        with closing(self._connect()) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported persistent lease schema")
            db.execute(
                """CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    request_id TEXT UNIQUE NOT NULL,
                    owner_id TEXT UNIQUE NOT NULL,
                    claim TEXT NOT NULL,
                    owner_epoch INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    native_id TEXT,
                    cleanup_confirmed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            encoded = json.dumps(asdict(self.capacity), sort_keys=True)
            row = db.execute("SELECT value FROM settings WHERE key='capacity'").fetchone()
            if row is None:
                db.execute("INSERT INTO settings VALUES ('capacity', ?)", (encoded,))
            elif row[0] != encoded:
                raise ValueError("lease capacity differs from persisted scheduler configuration")
            db.execute("PRAGMA user_version=1")
            db.commit()
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _claim_payload(claim: ResourceClaim) -> str:
        return json.dumps(asdict(claim), sort_keys=True)

    @staticmethod
    def _lease(row: sqlite3.Row) -> PersistentResourceLease:
        return PersistentResourceLease(
            lease_id=row["lease_id"],
            claim=ResourceClaim(**json.loads(row["claim"])),
            owner_epoch=int(row["owner_epoch"]),
            state=PersistentLeaseState(row["state"]),
            native_id=row["native_id"],
            cleanup_confirmed=bool(row["cleanup_confirmed"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def acquire(self, claim: ResourceClaim) -> PersistentLeaseDecision:
        payload = self._claim_payload(claim)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM leases WHERE request_id=? OR owner_id=?",
                (claim.request_id, claim.owner_id),
            ).fetchone()
            if existing is not None:
                if existing["claim"] != payload:
                    raise ValueError("lease request or owner already has a different claim")
                db.commit()
                return PersistentLeaseDecision(AllocationStatus.GRANTED, self._lease(existing))

            impossible = self._capacity_shortages(claim)
            if impossible:
                db.commit()
                return PersistentLeaseDecision(AllocationStatus.UNSATISFIABLE, shortages=impossible)
            active = db.execute(
                "SELECT * FROM leases WHERE state != ? ORDER BY created_at, lease_id",
                (PersistentLeaseState.RELEASED.value,),
            ).fetchall()
            temporary = self._temporary_shortages(claim, active)
            if temporary:
                db.commit()
                return PersistentLeaseDecision(AllocationStatus.WAITING, shortages=temporary)

            timestamp = _now()
            lease_id = "lease_" + uuid.uuid4().hex
            db.execute(
                "INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    lease_id,
                    claim.request_id,
                    claim.owner_id,
                    payload,
                    1,
                    PersistentLeaseState.ALLOCATED.value,
                    None,
                    0,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                ),
            )
            row = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
            db.commit()
        assert row is not None
        return PersistentLeaseDecision(AllocationStatus.GRANTED, self._lease(row))

    def get(self, lease_id: str) -> PersistentResourceLease:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise KeyError(lease_id)
        return self._lease(row)

    def list(self) -> tuple[PersistentResourceLease, ...]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM leases ORDER BY created_at, lease_id").fetchall()
        return tuple(self._lease(row) for row in rows)

    def bind_native(
        self, lease_id: str, owner_epoch: int, *, backend: str, native_id: str
    ) -> PersistentResourceLease:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, lease_id, owner_epoch)
            claim = ResourceClaim(**json.loads(row["claim"]))
            if claim.backend != backend:
                raise ValueError("native backend differs from the admitted lease")
            if row["native_id"] not in (None, native_id):
                raise ValueError("lease is already bound to another native job")
            if row["state"] == PersistentLeaseState.RELEASED.value:
                raise ValueError("released lease cannot bind a native job")
            db.execute(
                "UPDATE leases SET native_id=?, state=?, updated_at=? WHERE lease_id=?",
                (native_id, PersistentLeaseState.ACTIVE.value, _now().isoformat(), lease_id),
            )
            updated = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
            db.commit()
        assert updated is not None
        return self._lease(updated)

    def reconcile(self, lease_id: str, owner_epoch: int, reason: str) -> PersistentResourceLease:
        if not reason:
            raise ValueError("reconciliation reason is required")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, lease_id, owner_epoch)
            if row["state"] != PersistentLeaseState.RELEASED.value:
                db.execute(
                    "UPDATE leases SET state=?, updated_at=? WHERE lease_id=?",
                    (PersistentLeaseState.RECONCILING.value, _now().isoformat(), lease_id),
                )
            updated = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
            db.commit()
        assert updated is not None
        return self._lease(updated)

    def release(
        self, lease_id: str, owner_epoch: int, *, cleanup_confirmed: bool
    ) -> PersistentResourceLease:
        if not cleanup_confirmed:
            raise ValueError("lease release requires positive cleanup evidence")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, lease_id, owner_epoch)
            db.execute(
                "UPDATE leases SET state=?, cleanup_confirmed=1, updated_at=? WHERE lease_id=?",
                (PersistentLeaseState.RELEASED.value, _now().isoformat(), lease_id),
            )
            updated = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
            db.commit()
        assert updated is not None
        return self._lease(updated)

    @staticmethod
    def _owned(db: sqlite3.Connection, lease_id: str, owner_epoch: int) -> sqlite3.Row:
        row = db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise KeyError(lease_id)
        if int(row["owner_epoch"]) != owner_epoch:
            raise ValueError("stale lease owner epoch")
        return cast(sqlite3.Row, row)

    def _capacity_shortages(self, claim: ResourceClaim) -> tuple[ResourceShortage, ...]:
        shortages = []
        for name, requested, available in (
            ("cpu_cores", claim.cpu_cores, self.capacity.cpu_cores),
            ("memory_bytes", claim.memory_bytes, self.capacity.memory_bytes),
            ("gpus", claim.gpu_count, self.capacity.gpu_count),
        ):
            if requested is not None and available is not None and requested > available:
                shortages.append(
                    ResourceShortage(
                        name,
                        requested,
                        available,
                        "request exceeds the persisted scheduler capacity",
                    )
                )
        return tuple(shortages)

    def _temporary_shortages(
        self, claim: ResourceClaim, active: Sequence[sqlite3.Row]
    ) -> tuple[ResourceShortage, ...]:
        if len(active) >= self.capacity.max_concurrent:
            return (
                ResourceShortage(
                    "concurrency_slots",
                    1,
                    0,
                    "authorized benchmark slots are held by durable leases",
                ),
            )
        shortages = []
        claims = [ResourceClaim(**json.loads(row["claim"])) for row in active]
        for name, requested, available in (
            ("cpu_cores", claim.cpu_cores, self.capacity.cpu_cores),
            ("memory_bytes", claim.memory_bytes, self.capacity.memory_bytes),
            ("gpus", claim.gpu_count, self.capacity.gpu_count),
        ):
            if requested is None or available is None:
                continue
            attribute = name if name != "gpus" else "gpu_count"
            used = sum(getattr(item, attribute) or 0 for item in claims)
            if requested > available - used:
                shortages.append(
                    ResourceShortage(
                        name,
                        requested,
                        max(0, available - used),
                        "authorized capacity is held by durable leases",
                    )
                )
        return tuple(shortages)
