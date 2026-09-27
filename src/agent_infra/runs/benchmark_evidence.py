"""Bounded, run-scoped access to archived native evidence through Records contracts."""

import base64
import json
from typing import Any

from agent_infra.records.api import BlobRef, DataClass, RecordsReader, Visibility


class BenchmarkEvidence:
    def __init__(self, records: RecordsReader | None, run: dict[str, Any]) -> None:
        self.records, self.run = records, run
        self.files: list[dict[str, Any]] = []
        artifact_id = (run.get("result") or {}).get("artifact_id")
        if records is None or not artifact_id:
            return
        for artifact in records.list_artifacts(run["attempt_id"]):
            if (
                artifact.artifact_id == artifact_id
                and artifact.name == "native-submission"
                and artifact.visibility != Visibility.EVALUATOR
                and artifact.data_class
                not in {DataClass.PRIVATE_EVALUATION, DataClass.CREDENTIAL, DataClass.SECRET}
            ):
                if artifact.manifest_blob.size_bytes > 16 * 1024**2:
                    raise ValueError("artifact manifest exceeds preview limit")
                with records.open_blob(artifact.manifest_blob) as stream:
                    self.files = json.load(stream)["files"]
                break

    def read(self, member: str, *, maximum: int = 16 * 1024**2) -> bytes:
        file = next((item for item in self.files if item["path"] == member), None)
        if file is None:
            raise KeyError(member)
        ref = BlobRef(**file["blob"])
        if ref.size_bytes > maximum:
            raise ValueError("文件超过 16 MiB，请使用 Records CLI 导出")
        assert self.records is not None
        with self.records.open_blob(ref) as stream:
            return stream.read(maximum + 1)

    def inventory(self) -> dict[str, Any]:
        return {"files": [{"path": f["path"], "size_bytes": f["size_bytes"]} for f in self.files]}

    def file(self, member: str) -> dict[str, Any]:
        data = self.read(member)
        return {
            "member": member,
            "content_base64": base64.b64encode(data).decode(),
            "size_bytes": len(data),
        }

    def trajectory(
        self, *, cursor: int = 0, limit: int = 50, search: str = "", kind: str = "all"
    ) -> dict[str, Any]:
        if not 0 <= cursor <= 100000 or not 1 <= limit <= 100 or len(search) > 200:
            raise ValueError("invalid trajectory query")
        if kind not in {"all", "errors", "tools", "agent"}:
            raise ValueError("invalid trajectory filter")
        native = (self.run.get("result") or {}).get("native_result") or {}
        evidence = native.get("evidence") or {}
        trajectory = evidence.get("trajectory") or {"capture_status": "unavailable"}
        plan = self.run["request"]["execution"]["frozen_plan"]["plan"]
        base = {
            "run_id": self.run["run_id"],
            "attempt_id": self.run["attempt_id"],
            "instance_id": native.get("instance_id") or plan["units"][0]["native_id"],
            "prompt_level": native.get("prompt_level"),
            "session_id": trajectory.get("session_id"),
            "capture_status": evidence.get("capture_status", "unavailable"),
            "trajectory": trajectory,
            "docker": evidence.get("docker") or {},
            "calls": evidence.get("calls") or {},
            "files": evidence.get("files") or {},
        }
        steps = []
        # Prefer complete normalized ASI evidence when available; retain old bounded projections.
        available = {f["path"] for f in self.files}
        member = trajectory.get("member")
        full = "outputs/evidence/trajectory.json"
        if full in available:
            member = full
        if member in available and member in {full, "outputs/evidence/trajectory-view.json"}:
            try:
                value = json.loads(self.read(member))
                if isinstance(value, list):
                    steps = value
            except ValueError:
                if member == full and trajectory.get("member") in available:
                    steps = json.loads(self.read(trajectory["member"]))
        normalized = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            metadata = step.get("metadata") or {}
            text = str(step.get("content", ""))
            step_type = str(step.get("step_type", "unknown"))
            error = metadata.get("is_error") is True or metadata.get("exit_code") not in (
                None,
                0,
                "0",
            )
            if kind == "errors" and not error:
                continue
            if kind == "tools" and "tool" not in step_type:
                continue
            if kind == "agent" and ("tool" in step_type or metadata.get("role") == "user"):
                continue
            if (
                search.casefold()
                not in (text + json.dumps(metadata, ensure_ascii=False)).casefold()
            ):
                continue
            normalized.append(
                {
                    "step_index": step.get("step_index", index),
                    "timestamp_ms": step.get("timestamp_ms"),
                    "step_type": step_type,
                    "content": text[:65536],
                    "content_truncated": len(text) > 65536,
                    "metadata": {
                        k: v
                        for k, v in metadata.items()
                        if k
                        in {
                            "role",
                            "tool_name",
                            "parent_tool_name",
                            "is_error",
                            "exit_code",
                            "tool_call_id",
                            "call_id",
                            "duration_ms",
                        }
                        and isinstance(v, (str, int, float, bool))
                    },
                }
            )
        page = normalized[cursor : cursor + limit]
        return {
            **base,
            "steps": page,
            "matched_steps": len(normalized),
            "search_scope": member,
            "next_cursor": cursor + len(page) if cursor + len(page) < len(normalized) else None,
        }
