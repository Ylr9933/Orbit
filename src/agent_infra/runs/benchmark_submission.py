"""Durable one-shot native submission handoff with conservative uncertain-outcome handling."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agent_infra.benchmarks.api import AdapterIdentity, ExecutionPlan
from agent_infra.benchmarks.submission_api import (
    NativeSubmissionPlan,
    NativeSubmissionReceipt,
    SubmissionHandoff,
)
from agent_infra.records.api import ArtifactRef, RecordsReader


class BenchmarkSubmissionService:
    def __init__(self, root: Path, records: RecordsReader) -> None:
        self.root = root
        self.records = records
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("invalid benchmark run ID")
        return self.root / f"{run_id}.json"

    @contextmanager
    def _exclusive(self, run_id: str) -> Iterator[Path]:
        path = self._path(run_id)
        fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield path
        finally:
            os.close(fd)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if path.is_symlink():
            raise ValueError("submission state cannot be a symlink")
        return dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write(path: Path, document: dict[str, Any]) -> None:
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(document, output, sort_keys=True, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if path.is_symlink():
                raise ValueError("submission state cannot be a symlink")
            temporary.replace(path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def prepare(
        self,
        run: dict[str, Any],
        identity: AdapterIdentity,
        native_plan: Callable[[ExecutionPlan, ArtifactRef, dict[str, Any]], NativeSubmissionPlan],
    ) -> dict[str, Any]:
        result = run.get("result") or {}
        if (
            run["state"] != "finished"
            or result.get("execution") != "completed"
            or result.get("protocol") != "valid"
            or result.get("cleanup_complete") is not True
            or not result.get("artifact_id")
        ):
            raise ValueError(
                "native handoff requires a completed, valid and cleaned trial artifact"
            )
        execution = run["request"]["execution"]
        frozen = execution["frozen_plan"]
        if AdapterIdentity.model_validate_json(json.dumps(frozen["adapter"])) != identity:
            raise ValueError("adapter identity differs from frozen execution")
        plan = ExecutionPlan.model_validate_json(json.dumps(frozen["plan"]))
        artifact = self.records.get_artifact(result["artifact_id"])
        if artifact not in self.records.list_artifacts(run["attempt_id"]):
            raise ValueError("submission artifact belongs to another attempt")
        native = result.get("native_result") or {}
        prepared = native_plan(plan, artifact, native)
        if not isinstance(prepared, NativeSubmissionPlan):
            raise ValueError("adapter must return NativeSubmissionPlan")
        prepared = NativeSubmissionPlan.model_validate_json(prepared.model_dump_json())
        operation_id = (
            "submit-" + hashlib.sha256((run["run_id"] + artifact.digest).encode()).hexdigest()
        )
        handoff = SubmissionHandoff(
            operation_id=operation_id,
            run_id=run["run_id"],
            attempt_id=run["attempt_id"],
            candidate_id=plan.request.candidate.candidate_id,
            adapter=identity,
            suite_digest=plan.suite.source.digest,
            runner_digest=plan.suite.runner.digest,
            artifact_id=artifact.artifact_id,
            artifact_digest=artifact.digest,
            plan=prepared,
        )
        with self._exclusive(run["run_id"]) as path:
            if path.exists():
                previous = self._read(path)
                if previous["handoff"] != handoff.model_dump(mode="json"):
                    raise ValueError("native handoff changed for an existing operation")
                return previous
            document = {
                "handoff": handoff.model_dump(mode="json"),
                "state": "prepared",
                "receipt": None,
            }
            self._write(path, document)
            return document

    def status(self, run_id: str) -> dict[str, Any]:
        with self._exclusive(run_id) as path:
            if not path.is_file():
                raise KeyError(run_id)
            return self._read(path)

    def send(
        self,
        run_id: str,
        sender: Callable[[SubmissionHandoff, ArtifactRef, RecordsReader], NativeSubmissionReceipt],
    ) -> dict[str, Any]:
        with self._exclusive(run_id) as path:
            document = self._read(path)
            if document["state"] != "prepared":
                raise ValueError(
                    "submission already sent or outcome uncertain; do not retry blindly"
                )
            handoff = SubmissionHandoff.model_validate_json(json.dumps(document["handoff"]))
            if not handoff.plan.supports_send:
                raise ValueError("native adapter only supports manual handoff")
            artifact = self.records.get_artifact(handoff.artifact_id)
            if artifact.digest != handoff.artifact_digest:
                raise ValueError("submission artifact changed")
            document["state"] = "unknown"
            self._write(path, document)  # Durable intent precedes the irreversible call.
            receipt = sender(handoff, artifact, self.records)
            if not isinstance(receipt, NativeSubmissionReceipt):
                raise ValueError("adapter must return NativeSubmissionReceipt")
            document["receipt"] = NativeSubmissionReceipt.model_validate_json(
                receipt.model_dump_json()
            ).model_dump(mode="json")
            document["state"] = receipt.status
            self._write(path, document)
            return document
