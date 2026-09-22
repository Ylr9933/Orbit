"""Single atomic benchmark execution using existing control intents and Records.

No benchmark-specific branches, queue, scoring or numeric resource allocator.
The durable execution slot remains held until cleanup AND evidence collection succeed.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from agent_infra.benchmarks.execution import PreparedExecution, execution_spec, validate_backend
from agent_infra.environments.execution_api import ExecutionBackend, ExecutionHandle
from agent_infra.records.api import (
    AttemptManifest,
    CaptureStatus,
    DataClass,
    EventDraft,
    ProducerKind,
    RecordContext,
    RecordSink,
    RecordsReader,
    RecordsWriter,
    RunManifest,
    Visibility,
)
from agent_infra.runs.control_store import RunControlStore


class ExecutionRecords(RecordsWriter, RecordsReader, Protocol):
    pass


class BenchmarkExecutionService:
    def __init__(
        self,
        store: RunControlStore,
        records: ExecutionRecords,
        backend: ExecutionBackend,
        workspace_root: Path,
    ) -> None:
        self.store, self.records, self.backend, self.workspace_root = (
            store,
            records,
            backend,
            workspace_root,
        )

    def submit(self, operation_id: str, execution: PreparedExecution) -> dict[str, Any]:
        if not operation_id or len(operation_id) > 128:
            raise ValueError("operation_id must contain 1–128 characters")
        validate_backend(execution, self.backend.backend_id, self.backend.features)
        payload = {"kind": "benchmark", "execution": execution.model_dump(mode="json")}
        with self.store.exclusive():
            run = self.store.lookup(operation_id, payload)
            if run is None:
                if self.store.unfinished():
                    raise ValueError(
                        "benchmark execution slot held; reconcile/collect the existing Run"
                    )
                run = self.store.create(
                    operation_id,
                    payload,
                    {
                        "benchmark": execution.frozen_plan.plan.suite.benchmark,
                        "plan_digest": execution.frozen_plan.digest,
                    },
                )
            return self._advance(run, allow_submit=True)

    def status(self, run_id: str, *, cancel: bool = False) -> dict[str, Any]:
        with self.store.exclusive():
            run = self.store.get(run_id)
            if cancel and run["state"] != "finished":
                run = self.store.update(run_id, cancel_requested=True)
            return self._advance(run)

    def reconcile(self) -> list[dict[str, Any]]:
        # Recovery observes existing intents only, never automatically resubmits.
        return [self.status(run["run_id"]) for run in self.store.unfinished()]

    def _sink(self, run: dict[str, Any], execution: PreparedExecution) -> RecordSink:
        timestamp = datetime.fromisoformat(run["created_at"])
        self.records.begin_run(
            RunManifest(
                run["run_id"],
                timestamp,
                {
                    "kind": "benchmark",
                    "execution_digest": execution.digest,
                    **run["lineage"],
                },
            )
        )
        self.records.begin_attempt(
            AttemptManifest(
                run["attempt_id"],
                run["run_id"],
                timestamp,
                task_id=execution.frozen_plan.plan.units[0].unit_id,
                task_digest=execution.frozen_plan.digest,
                coverage={
                    "agent_native": "not_instrumented",
                    "process_output": "bounded_raw",
                    "resources": "not_allocated",
                    "cleanup": "backend_scope",
                },
            )
        )
        sink = self.records.scoped_sink(
            RecordContext(
                run["run_id"],
                run["attempt_id"],
                "benchmark:" + run["attempt_id"],
                ProducerKind.RUN,
                phase_id=execution.frozen_plan.plan.phases[0].phase_id,
            )
        )
        sink.start_stream(
            run["attempt_id"] + ":combined",
            "native/combined",
            visibility=Visibility.ADMIN,
            data_class=DataClass.USER_PRIVATE,
        )
        return sink

    @staticmethod
    def _event(sink: RecordSink, name: str, payload: dict[str, Any]) -> None:
        sequence = (
            "execution.requested",
            "execution.started",
            "execution.finished",
            "execution.cleanup_confirmed",
            "execution.slot_released",
        ).index(name)
        sink.append_events(
            (
                EventDraft(
                    name,
                    payload,
                    producer_sequence=sequence,
                    idempotency_key=f"{sink.context.producer_id}:{name}",
                    visibility=Visibility.ADMIN,
                ),
            )
        )

    def _advance(self, run: dict[str, Any], *, allow_submit: bool = False) -> dict[str, Any]:
        if run["state"] == "finished":
            return run
        execution = PreparedExecution.model_validate_json(json.dumps(run["request"]["execution"]))
        sink = self._sink(run, execution)
        # Records may have committed before the control-store completion acknowledgement.
        attempt = self.records.get_attempt(run["attempt_id"])
        if attempt.status != "running":
            self.records.finish_run(run["run_id"], status=attempt.status)
            return self.store.update(
                run["run_id"], state="finished", slot_held=False, result=dict(attempt.result or {})
            )
        backend_operation = run["attempt_id"]
        spec = execution_spec(
            execution, run["run_id"], run["attempt_id"], self.workspace_root / run["run_id"]
        )
        self._event(
            sink,
            "execution.requested",
            {"operation_id": run["operation_id"], "spec_digest": spec.digest()},
        )
        receipt = self.backend.reconcile(backend_operation)
        if receipt.state == "not_submitted":
            if run["cancel_requested"]:
                return self._finish(run, sink, "cancelled", None, None, False, (), "never_launched")
            if not allow_submit:
                return self.store.update(
                    run["run_id"],
                    state="accepted",
                    slot_held=True,
                    detail="not submitted; replay the same explicit operation to launch",
                )
            self.store.update(run["run_id"], state="submitting", slot_held=True)
            try:
                self.backend.submit(backend_operation, spec)
            except Exception as error:
                # The reply can be lost after launch. Persist uncertainty; never retry here.
                return self.store.update(
                    run["run_id"],
                    state="quarantined",
                    slot_held=True,
                    detail=f"submit unconfirmed: {type(error).__name__}",
                )
            receipt = self.backend.reconcile(backend_operation)
        handle = receipt.handle
        if handle is None:
            return self.store.update(
                run["run_id"],
                state="quarantined",
                slot_held=True,
                detail=receipt.reason or "backend identity unavailable",
            )
        if handle.spec_digest != spec.digest():
            raise ValueError("reconciled operation belongs to a different execution spec")
        run = self.store.update(run["run_id"], handle=asdict(handle), slot_held=True)
        if handle.native_id:
            self._event(
                sink,
                "execution.started",
                {"native_id": handle.native_id, "backend": handle.backend},
            )
        if run["cancel_requested"]:
            self.backend.cancel(handle)
        cursor = run.get("cursor", 0)
        while True:
            observation = self.backend.observe(handle, cursor)
            if observation.data:
                sink.append_stream(run["attempt_id"] + ":combined", observation.data, cursor)
                cursor = observation.next_cursor
                run = self.store.update(run["run_id"], cursor=cursor)
            if observation.eof or not observation.data:
                break
        if observation.status in {"running", "unknown"}:
            return self.store.update(
                run["run_id"],
                state="running" if observation.status == "running" else "quarantined",
                detail=receipt.reason,
                slot_held=True,
            )
        cleanup = self.backend.cleanup(handle)
        if not cleanup.complete:
            return self.store.update(
                run["run_id"], state="quarantined", slot_held=True, detail=cleanup.reason
            )
        return self._collect(
            run, sink, handle, observation.status, observation.exit_code, observation.logs_truncated
        )

    def _collect(
        self,
        run: dict[str, Any],
        sink: RecordSink,
        handle: ExecutionHandle,
        status: str,
        exit_code: int | None,
        truncated: bool,
    ) -> dict[str, Any]:
        try:
            submission = self.backend.collect(handle)
            artifacts = [
                item
                for item in self.records.list_artifacts(run["attempt_id"])
                if item.name == "native-submission" and item.digest == submission.digest
            ]
            artifact = (
                artifacts[0]
                if artifacts
                else sink.commit_artifact(
                    submission.root, name="native-submission", visibility=Visibility.ADMIN
                )
            )
            return self._finish(
                run,
                sink,
                status,
                exit_code,
                artifact.artifact_id,
                truncated,
                submission.missing,
                self.backend.cleanup_scope,
            )
        except (OSError, ValueError, RuntimeError) as error:
            # Keep the source spool and slot; a later status/reconcile retries collection only.
            return self.store.update(
                run["run_id"],
                state="collecting",
                slot_held=True,
                detail=f"evidence collection failed: {type(error).__name__}",
            )

    def _finish(
        self,
        run: dict[str, Any],
        sink: RecordSink,
        status: str,
        exit_code: int | None,
        artifact_id: str | None,
        truncated: bool,
        missing: tuple[str, ...],
        scope: str,
    ) -> dict[str, Any]:
        capture = CaptureStatus.TRUNCATED if truncated else CaptureStatus.COMPLETE
        stream = sink.finalize_stream(run["attempt_id"] + ":combined", capture)
        result = {
            "execution": status,
            "exit_code": exit_code,
            "evaluation": "not_interpreted",
            "protocol": "not_validated",
            "cleanup_complete": True,
            "cleanup_scope": scope,
            "capture": "partial" if missing else capture.value,
            "missing_outputs": list(missing),
            "artifact_id": artifact_id,
            "stream": asdict(stream),
        }
        self._event(sink, "execution.finished", result)
        self._event(sink, "execution.cleanup_confirmed", {"scope": scope})
        # Release only after both durable evidence and a positive cleanup receipt.
        self._event(sink, "execution.slot_released", {"cleanup_confirmed": True})
        self.records.finish_attempt(run["attempt_id"], status=status, result=result)
        self.records.finish_run(run["run_id"], status=status)
        return self.store.update(
            run["run_id"], state="finished", slot_held=False, result=result, detail=None
        )
