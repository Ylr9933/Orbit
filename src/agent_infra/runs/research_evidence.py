"""Capture platform tool calls and bounded Job streams into existing Records."""

import base64
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_infra.environments.api import EnvironmentHandle
from agent_infra.environments.job_api import ResearchEnvironment
from agent_infra.records.api import (
    CaptureStatus,
    EventDraft,
    ProducerKind,
    RecordContext,
    RecordSink,
    Visibility,
)
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.research_store import ResearchStore


class ResearchEvidence:
    def __init__(
        self, records: LocalRecordsStore, store: ResearchStore, environment: ResearchEnvironment
    ) -> None:
        self.records, self.store, self.env = records, store, environment

    def sink(self, run: dict[str, Any], session: str = "controller") -> RecordSink:
        return self.records.scoped_sink(
            RecordContext(
                run["run_id"],
                run["attempt_id"],
                "research:" + run["run_id"] + ":" + session,
                ProducerKind.ENVIRONMENT,
                session_id=session,
            )
        )

    def event(
        self, run: dict[str, Any], session: str, call_id: str, name: str, payload: dict[str, Any]
    ) -> None:
        # Large input/output goes to blobs; canonical events carry bounded references.
        sink = self.sink(run, session)
        blob = sink.put_blob(
            json.dumps(payload, default=str).encode(), media_type="application/json"
        )

        sink.append_events(
            (
                EventDraft(
                    name,
                    {
                        "tool_call_id": call_id,
                        "tool_name": payload["tool_name"],
                        "payload_blob": asdict(blob),
                    },
                    idempotency_key=f"{call_id}:{name}",
                    span_id="tool_" + call_id,
                    correlation={
                        "project_id": run["lineage"]["project_id"],
                        "external_session_id": session,
                        "tool_call_id": call_id,
                    },
                    raw_refs=(blob.digest,),
                    visibility=Visibility.USER,
                ),
            )
        )

    def native_sink(self, run: dict[str, Any], session: str) -> RecordSink:
        return self.records.scoped_sink(
            RecordContext(
                run["run_id"],
                run["attempt_id"],
                "host-agent:" + run["run_id"] + ":" + session,
                ProducerKind.AGENT,
                session_id=session,
            )
        )

    def log_path(self, job: dict[str, Any]) -> Path:
        directory = self.store.root / "job-logs"
        directory.mkdir(exist_ok=True, mode=0o700)
        return directory / str(job["job_id"])

    def poll(self, run: dict[str, Any], job: dict[str, Any]) -> None:
        sink = self.sink(run)
        while True:
            result = self.env.logs(
                EnvironmentHandle(run["environment_id"]), job["job_id"], job["cursor"]
            )
            data = base64.b64decode(result["content_base64"], validate=True)
            if data:
                with self.log_path(job).open("ab") as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                sink.append_stream(job["job_id"], data, job["cursor"])
                job["cursor"] += len(data)
            if result["state"] == "running" or not data:
                break
        job.update({k: result[k] for k in ("state", "exit_code", "logs_truncated")})
        self.store.save_job(job)
        if job["state"] != "running":
            capture = CaptureStatus.TRUNCATED if job["logs_truncated"] else CaptureStatus.COMPLETE
            job["capture_status"] = capture.value
            self.store.save_job(job)
            self.finalize_log(run, job, capture)

    def finalize_log(
        self, run: dict[str, Any], job: dict[str, Any], capture: CaptureStatus
    ) -> None:
        sink = self.sink(run)
        sink.start_stream(
            job["job_id"], f"job/{job['job_id']}/combined", visibility=Visibility.USER
        )
        stream = sink.finalize_stream(job["job_id"], capture)
        sink.append_events(
            (
                EventDraft(
                    "process.exited",
                    {"job_id": job["job_id"], "status": job["state"], "stream": asdict(stream)},
                    idempotency_key="exit:" + job["job_id"],
                    producer_sequence=int(job["job_id"][:12], 16),
                    correlation={
                        "job_id": job["job_id"],
                        "tool_call_id": str(job["tool_call_id"]),
                        "external_session_id": job["session_id"],
                    },
                    capture_status=capture,
                ),
            )
        )

        job["log_finalized"] = True
        self.store.save_job(job)
