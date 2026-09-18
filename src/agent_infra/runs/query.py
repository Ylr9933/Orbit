"""Controlled Records reads scoped by durable Run and Artifact identities."""

import base64
import json
from dataclasses import asdict
from typing import Any

from agent_infra.records import AttemptTrajectoryBuilder, BlobRef, DataClass, EventQuery, Visibility
from agent_infra.records.api import RecordsReader
from agent_infra.runs.control_store import RunControlStore

_PRIVATE = {DataClass.PRIVATE_EVALUATION, DataClass.CREDENTIAL, DataClass.SECRET}


class RunQueries:
    def __init__(self, commands: RunControlStore, records: RecordsReader) -> None:
        self.commands, self.records = commands, records

    def status(self, run_id: str) -> dict[str, Any]:
        entry = self.commands.get(run_id)
        entry["attempts"] = [asdict(item) for item in self.records.list_attempts(run_id)]
        return entry

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        entry = self.commands.get(run_id)
        return [
            asdict(item)
            for item in self.records.list_artifacts(entry["attempt_id"])
            if item.data_class not in _PRIVATE
            and item.visibility in {Visibility.USER, Visibility.AGENT}
        ]

    def artifact(self, run_id: str, artifact_id: str, member: str | None = None) -> dict[str, Any]:
        allowed = {item["artifact_id"] for item in self.artifacts(run_id)}
        if artifact_id not in allowed:
            raise KeyError(artifact_id)
        artifact = self.records.get_artifact(artifact_id)
        with self.records.open_blob(artifact.manifest_blob) as file:
            manifest = json.load(file)
        if member is None:
            return {
                "artifact_id": artifact_id,
                "files": [
                    {"path": item["path"], "size_bytes": item["size_bytes"]}
                    for item in manifest["files"]
                ],
            }
        # Exact manifest membership, never resolve a caller-supplied host path.
        match = next((item for item in manifest["files"] if item["path"] == member), None)
        if match is None:
            raise KeyError(member)
        ref = BlobRef(**match["blob"])
        if ref.size_bytes > 16 * 1024**2:
            raise ValueError("file exceeds 16 MiB HTTP download limit; use local Records storage")
        with self.records.open_blob(ref) as file:
            data = file.read(16 * 1024**2 + 1)
        if len(data) != ref.size_bytes:
            raise ValueError("stored artifact size mismatch")
        return {
            "path": member,
            "size_bytes": len(data),
            "content_base64": base64.b64encode(data).decode(),
        }

    def events(self, run_id: str, cursor: str | None = None) -> dict[str, Any]:
        entry = self.commands.get(run_id)
        page = self.records.read_events(EventQuery(attempt_id=entry["attempt_id"]), cursor)
        return {
            "items": [
                asdict(event)
                for event in page.items
                if event.data_class not in _PRIVATE
                and event.visibility not in {Visibility.EVALUATOR, Visibility.ADMIN}
            ],
            "next_cursor": page.next_cursor,
        }

    def trajectory(self, run_id: str) -> dict[str, Any]:
        entry = self.commands.get(run_id)
        return asdict(AttemptTrajectoryBuilder(self.records).build(entry["attempt_id"]))
