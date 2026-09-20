"""Bounded environment workflow. Reuses Run admission, Records and Docker recovery."""

import json
import threading
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from agent_infra.environments.preparation_api import (
    SMOKE_VERSION,
    TEMPLATE_VERSION,
    EnvironmentIntent,
    EnvironmentPreparer,
    EnvironmentProposal,
    PreparationResult,
    digest,
)
from agent_infra.environments.preparation_locks import resolve_environment_lock
from agent_infra.environments.preparation_store import EnvironmentCatalog
from agent_infra.records.api import (
    AttemptManifest,
    EventDraft,
    ProducerKind,
    RecordContext,
    RunManifest,
    Visibility,
)
from agent_infra.resources.api import ResourceRequest
from agent_infra.runs.controller import LocalRunController


class EnvironmentPreparation:
    def __init__(
        self, control: LocalRunController, catalog: EnvironmentCatalog, backend: EnvironmentPreparer
    ) -> None:
        self.control, self.catalog, self.backend = control, catalog, backend
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._active: tuple[str, str] | None = None
        self._closed = False
        # Docker and Run recovery happened under the Controller host lock first.
        for plan in catalog.list():
            for attempt in plan["attempts"]:
                if attempt["status"] == "running":
                    attempt.update(
                        status="interrupted",
                        cleanup_complete=True,
                        error="controller restarted; retry requires a new operation",
                    )
                    # Full reserved time remains spent after a crash: no budget windfall.
                    catalog.save(plan)

    def call(
        self,
        project: str,
        session: str,
        action: str,
        options: dict[str, Any],
        operation: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise ValueError("environment service is stopping")
            if action == "environment_plan":
                intent = EnvironmentIntent.from_dict(options["intent"])
                base = self.backend.resolve(intent.base_image, intent.agent)
                plan: dict[str, Any] = {
                    "plan_id": str(operation),
                    "project_id": project,
                    "session_id": session,
                    "intent": intent.to_dict(),
                    "base_image_id": base,
                    "proposals": [],
                    "attempts": [],
                    "reserved_seconds": 0,
                    "created_at": time.time(),
                }
                self.catalog.save(plan)
                return plan
            if action == "environment_list":
                return {"items": self.catalog.list(project)}
            plan = self.catalog.get(project, options["plan_id"])
            if action == "environment_status":
                result = dict(plan)
                if options.get("attempt_id"):
                    attempt = next(
                        a for a in plan["attempts"] if a["attempt_id"] == options["attempt_id"]
                    )
                    path = self.catalog.root / attempt["attempt_id"] / "events.jsonl"
                    offset = options.get("cursor", 0)
                    if type(offset) is not int or offset < 0:
                        raise ValueError("cursor must be a nonnegative byte offset")
                    data = b""
                    if path.exists():
                        with path.open("rb") as file:
                            file.seek(offset)
                            data = file.read(32768)
                    result.update(log=data.decode(errors="replace"), next_cursor=offset + len(data))
                return result
            if action == "environment_propose":
                if self._active and self._active[0] == plan["plan_id"]:
                    raise ValueError("wait for the current environment attempt")
                if options["expected_revision"] != len(plan["proposals"]):
                    raise ValueError("proposal revision conflict; read environment_status")
                if len(plan["proposals"]) >= 20:
                    raise ValueError("proposal revision limit reached")
                intent = EnvironmentIntent.from_dict(plan["intent"])
                proposal = EnvironmentProposal.from_dict(options["proposal"], intent)
                plan["proposals"].append(
                    proposal.to_dict() | {"session_id": session, "created_at": time.time()}
                )
                self.catalog.save(plan)
                return plan
            if action == "environment_build":
                return self._start(plan, options["revision"], str(operation), session)
            if action == "environment_cancel":
                if self._active and self._active[0] == plan["plan_id"]:
                    self._cancel.set()
                return plan | {
                    "cancel_requested": bool(self._active and self._active[0] == plan["plan_id"])
                }
            raise ValueError("unknown environment action")

    def resolve(self, project: str, lock_id: str, *, agent: str | None = None) -> dict[str, Any]:
        with self._lock:
            return resolve_environment_lock(
                self.catalog, project, lock_id, self.backend.resolve, agent=agent
            )

    def _start(
        self, plan: dict[str, Any], revision: int, operation: str, session: str
    ) -> dict[str, Any]:
        if self._active:
            raise ValueError("environment preparation is busy; wait for cleanup")
        if type(revision) is not int or revision != len(plan["proposals"]) or revision < 1:
            raise ValueError("build requires the exact current proposal revision")
        intent = EnvironmentIntent.from_dict(plan["intent"])
        if (
            len(plan["attempts"]) >= intent.max_attempts
            or plan["reserved_seconds"] >= intent.total_seconds
        ):
            raise ValueError("environment budget exhausted; request a new user decision")
        source = plan["proposals"][-1]
        proposal = EnvironmentProposal.from_dict(
            {k: source[k] for k in ("dependencies", "source", "reason")}, intent
        )
        timeout = min(intent.attempt_seconds, intent.total_seconds - plan["reserved_seconds"])
        request = ResourceRequest(operation, intent.cpu, intent.memory_bytes)
        self.control.refresh()
        assessment = self.control.resources.assess(request)
        if assessment.shortages:
            raise ValueError(
                "resource unavailable: " + "; ".join(s.reason for s in assessment.shortages)
            )
        run = self.control.reserve_research(
            "environment:" + operation,
            {
                "kind": "environment",
                "plan_id": plan["plan_id"],
                "revision": revision,
                "session_id": session,
                "operation_id": operation,
            },
            plan["project_id"],
        )
        lease = None
        attempt: dict[str, Any] | None = None
        try:
            lease = self.control.resources.try_allocate(request).lease
            if lease is None:
                raise ValueError("resources changed during environment admission")
            self.control.store.update(run["run_id"], lease_id=lease.lease_id)
            now = datetime.now(UTC)
            self.control.records.begin_run(
                RunManifest(run["run_id"], now, run["request"] | {"project_id": plan["project_id"]})
            )
            self.control.records.begin_attempt(
                AttemptManifest(run["attempt_id"], run["run_id"], now)
            )
            attempt = {
                "attempt_id": uuid.uuid4().hex,
                "run_id": run["run_id"],
                "status": "running",
                "proposal_revision": revision,
                "reserved_seconds": timeout,
                "started_at": time.time(),
                "lock": None,
            }
            plan["attempts"].append(attempt)
            plan["reserved_seconds"] += timeout
            self.catalog.save(plan)
            self._active = (plan["plan_id"], attempt["attempt_id"])
            self._cancel = threading.Event()
            self._thread = threading.Thread(
                target=self._execute,
                args=(plan, attempt, run, lease.lease_id, intent, proposal, timeout),
                name="environment-preparation",
                daemon=False,
            )
            self._thread.start()
            return dict(json.loads(json.dumps(plan)))
        except Exception:
            if attempt is not None:
                attempt.update(
                    status="failed", cleanup_complete=True, error="worker could not start"
                )
                plan["reserved_seconds"] -= timeout
                self.catalog.save(plan)
            if lease:
                self.control.resources.release(lease.lease_id)
            self.control.store.update(
                run["run_id"],
                state="finished",
                result={"status": "failed", "cleanup_complete": True},
            )
            self.control.release_research(run["run_id"], clean=True)
            self._active = None
            raise

    def _execute(
        self,
        plan: dict[str, Any],
        attempt: dict[str, Any],
        run: dict[str, Any],
        lease_id: str,
        intent: EnvironmentIntent,
        proposal: EnvironmentProposal,
        timeout: float,
    ) -> None:
        started = time.monotonic()
        root = self.catalog.root / attempt["attempt_id"]
        sink = self.control.records.scoped_sink(
            RecordContext(
                run["run_id"],
                run["attempt_id"],
                "environment:preparation",
                ProducerKind.ENVIRONMENT,
                session_id=run["request"]["session_id"],
            )
        )
        key = digest(
            {
                "base": plan["base_image_id"],
                "dependencies": proposal.dependencies,
                "template": intent.template,
                "version": TEMPLATE_VERSION,
                "network": intent.network,
                "agent": intent.agent,
            }
        )
        result = PreparationResult("failed", None, False, {})
        try:
            root.mkdir(mode=0o700)

            def emit(event: str, payload: dict[str, Any]) -> None:
                with (root / "events.jsonl").open("a") as file:
                    file.write(
                        json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n"
                    )
                sink.append_events(
                    (
                        EventDraft(
                            "environment." + event,
                            payload,
                            visibility=Visibility.USER,
                            span_id="tool_" + run["request"]["operation_id"],
                            correlation={
                                "project_id": plan["project_id"],
                                "external_session_id": run["request"]["session_id"],
                            },
                        ),
                    )
                )

            emit(
                "requested",
                {
                    "intent": plan["intent"],
                    "proposal": proposal.to_dict(),
                    "plan_id": plan["plan_id"],
                    "revision": attempt["proposal_revision"],
                    "cache_key": key,
                    "lease_id": lease_id,
                },
            )
            self.control.store.update(run["run_id"], state="running")
            result = self.backend.execute(
                key=key,
                intent=intent,
                proposal=proposal,
                base=plan["base_image_id"],
                cached=self.catalog.cached(key),
                workspace=root,
                timeout=timeout,
                cancel=self._cancel,
                emit=emit,
            )
            if result.image_id and result.cleanup_complete and intent.template == "python-cpu":
                self.catalog.cache(
                    key,
                    {"image_id": result.image_id, "packages": result.details.get("packages", {})},
                )
            if self._cancel.is_set() and result.status == "ready":
                result = PreparationResult(
                    "cancelled", result.image_id, result.cleanup_complete, result.details
                )
            emit("completed", asdict(result))
            sink.commit_artifact(root / "events.jsonl", name="environment-log")
        except Exception as error:
            result = PreparationResult(
                "failed",
                result.image_id,
                result.cleanup_complete,
                {"error": f"preparation/recording failed: {type(error).__name__}"},
            )
        with self._lock:
            try:
                self._finish(
                    plan,
                    attempt,
                    run,
                    lease_id,
                    intent,
                    proposal,
                    timeout,
                    time.monotonic() - started,
                    key,
                    result,
                )
            except Exception:
                # Do not admit work after evidence or state could not be committed.
                self.control.release_research(run["run_id"], clean=False)
            finally:
                self._active = None

    def _finish(
        self,
        plan: dict[str, Any],
        attempt: dict[str, Any],
        run: dict[str, Any],
        lease_id: str,
        intent: EnvironmentIntent,
        proposal: EnvironmentProposal,
        timeout: float,
        elapsed: float,
        key: str,
        result: PreparationResult,
    ) -> None:
        attempt.update(asdict(result), elapsed_seconds=elapsed)
        plan["reserved_seconds"] -= max(0, timeout - attempt["elapsed_seconds"])
        if result.status == "ready" and result.cleanup_complete:
            now = time.time()
            attempt["lock"] = {
                "lock_id": plan["plan_id"] + ":" + attempt["attempt_id"],
                "project_id": plan["project_id"],
                "image_id": result.image_id,
                "base_image_id": plan["base_image_id"],
                "proposal_revision": attempt["proposal_revision"],
                "intent_digest": digest(plan["intent"]),
                "proposal_digest": digest(proposal.to_dict()),
                "cache_key": key,
                "template_version": TEMPLATE_VERSION,
                "smoke_version": SMOKE_VERSION,
                "agent": intent.agent,
                "validated_at": now,
                "expires_at": now + intent.valid_seconds,
                "context": "trusted template + pinned public requirements; "
                "no project files or credentials",
                "packages": result.details.get("packages", {}),
                "run_id": run["run_id"],
            }
        if result.cleanup_complete:
            self.control.resources.release(lease_id)
        outcome = asdict(result) | {
            "lease_released": result.cleanup_complete,
            "plan_id": plan["plan_id"],
        }
        self.control.records.finish_attempt(run["attempt_id"], status=result.status, result=outcome)
        self.control.records.finish_run(run["run_id"], status=result.status)
        self.control.store.update(
            run["run_id"],
            state="finished" if result.cleanup_complete else "quarantined",
            result=outcome,
        )
        self.control.release_research(run["run_id"], clean=result.cleanup_complete)
        self.catalog.save(plan)

    def close(self) -> bool:
        with self._lock:
            self._closed = True
            self._cancel.set()
        if self._thread:
            self._thread.join(timeout=90)
        return self._active is None
