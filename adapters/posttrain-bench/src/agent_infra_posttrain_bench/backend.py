"""Durable local engineering execution and native HTCondor job ownership."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from agent_infra.contracts.files import content_digest, resolve_material
from agent_infra.environments._process_state import locked
from agent_infra.environments.api import CleanupResult, Submission
from agent_infra.environments.execution_api import (
    ExecutionHandle,
    ExecutionObservation,
    ExecutionSpec,
    Reconciliation,
)
from agent_infra.environments.managed_process import ManagedProcessBackend
from agent_infra.environments.recovery import write_ownership

from .handoff import finalize
from .request import BACKEND, FEATURES, Request
from .source import SAFE_VALUE, parse_env_path, private_file, scheduler_digest

JOB_ID = re.compile(r"^(?P<cluster>[0-9]+)\.(?P<process>[0-9]+)$")
RUNNING = {1, 2, 6, 7}
REMOVED = 3
COMPLETED = 4


class _EngineeringBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_engineering_process_group"


def _atomic_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _request(spec: ExecutionSpec) -> Request:
    try:
        return Request.model_validate_json(spec.command.argv[-1])
    except (IndexError, ValueError) as error:
        raise ValueError("invalid PostTrainBench frozen invocation") from error


class PostTrainBackend:
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_condor_job_and_content_addressed_model_snapshot"

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError("PostTrainBench backend state must be private")
        self.engineering = _EngineeringBackend(self.root / "engineering")

    def _path(self, operation_id: str) -> Path:
        if not operation_id or len(operation_id) > 200:
            raise ValueError("invalid backend operation ID")
        return self.root / "condor" / hashlib.sha256(operation_id.encode()).hexdigest()

    def _kind(self, operation_id: str) -> str | None:
        if (self.engineering._path(operation_id) / "launch.json").exists():
            return "engineering"
        if (self._path(operation_id) / "intent.json").exists():
            return "native"
        return None

    @staticmethod
    def _binary(request: Request, name: str) -> Path:
        root = Path(request.scheduler_bin_dir)
        path = root / name
        if not root.is_absolute() or path.is_symlink() or not os.access(path, os.X_OK):
            raise ValueError(f"required scheduler command is unavailable: {name}")
        return path

    def _run(
        self, request: Request, name: str, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        if scheduler_digest(Path(request.scheduler_bin_dir)) != request.scheduler_digest:
            raise ValueError("scheduler commands changed after planning")
        return subprocess.run(
            [str(self._binary(request, name)), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def _query(self, request: Request, *, job_id: str | None, tag: str) -> list[dict[str, Any]]:
        selector = [job_id] if job_id else ["-constraint", f'AgentInfraOperationId == "{tag}"']
        active = self._run(request, "condor_q", *selector, "-json")
        if active.returncode:
            raise RuntimeError("condor_q failed")
        rows = self._rows(active.stdout)
        if rows:
            return rows
        history = self._run(request, "condor_history", *selector, "-limit", "2", "-json")
        if history.returncode:
            raise RuntimeError("condor_history failed")
        return self._rows(history.stdout)

    @staticmethod
    def _rows(value: str) -> list[dict[str, Any]]:
        document = json.loads(value or "[]")
        if not isinstance(document, list) or not all(isinstance(item, dict) for item in document):
            raise ValueError("scheduler JSON response is not a list of ClassAds")
        return cast(list[dict[str, Any]], document)

    @staticmethod
    def _job_id(row: dict[str, Any]) -> str:
        return f"{int(row['ClusterId'])}.{int(row.get('ProcId', 0))}"

    def _receipt(self, root: Path, request: Request, tag: str) -> dict[str, Any] | None:
        path = root / "receipt.json"
        if path.is_file():
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        rows = self._query(request, job_id=None, tag=tag)
        if len(rows) > 1:
            raise RuntimeError("multiple scheduler jobs share one operation identity")
        if not rows:
            return None
        receipt = {"job_id": self._job_id(rows[0]), "tag": tag}
        write_ownership(path, receipt)
        return receipt

    @staticmethod
    def _safe(value: str, field: str) -> str:
        if not SAFE_VALUE.fullmatch(value):
            raise ValueError(f"unsafe scheduler value: {field}")
        return value

    def _submit_file(self, root: Path, spec: ExecutionSpec, request: Request, tag: str) -> Path:
        checkout = request.checkout()
        config = checkout / ".env"
        private_file(config)
        configured_results = parse_env_path(config, "POST_TRAIN_BENCH_RESULTS_DIR", checkout)
        if configured_results != Path(request.results_root).resolve():
            raise ValueError("results_root differs from the private PostTrainBench configuration")
        for value, name in (
            (request.task, "task"),
            (request.agent, "agent"),
            (request.agent_config, "agent_config"),
            (request.model_to_train, "model_to_train"),
            (str(checkout), "checkout_root"),
            (str(root), "backend_state"),
            (str(Path.home()), "home"),
        ):
            self._safe(value, name)
        experiment = "_agentinfra_" + tag
        lines = [
            "universe = vanilla",
            "executable = /bin/bash",
            "initialdir = " + str(checkout),
            "arguments = "
            + " ".join(
                (
                    "src/run_task.sh",
                    request.task,
                    request.agent,
                    request.model_to_train,
                    "$(Cluster)",
                    str(request.num_hours),
                    request.agent_config,
                    str(request.num_gpus),
                )
            ),
            f'environment = "HOME={Path.home()} POST_TRAIN_BENCH_EXPERIMENT_NAME={experiment}"',
            "getenv = false",
            "should_transfer_files = NO",
            f"output = {root / 'scheduler.out'}",
            f"error = {root / 'scheduler.err'}",
            f"log = {root / 'scheduler.log'}",
            f"request_cpus = {request.request_cpus}",
            f"request_memory = {request.request_memory_mb}",
            f"request_disk = {request.request_disk_gb}G",
            f"request_gpus = {request.num_gpus}",
            'requirements = TARGET.CUDADeviceName == "NVIDIA H100 80GB HBM3"',
            f'+AgentInfraOperationId = "{tag}"',
            f'+AgentInfraSpecDigest = "{spec.digest()}"',
            "+AgentInfraRequiresExclusiveGpuVisibility = true",
            "queue 1",
        ]
        path = root / "job.sub"
        write_ownership(path, {"submit_description": lines})
        # condor_submit consumes text rather than JSON; keep the reviewed text beside its journal.
        submit = root / "job.condor"
        fd = os.open(submit, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        return submit

    def submit(self, operation_id: str, spec: ExecutionSpec) -> ExecutionHandle:
        spec = ExecutionSpec.model_validate_json(spec.model_dump_json())
        request = _request(spec)
        if request.mode == "engineering":
            return self.engineering.submit(operation_id, spec)
        root = self._path(operation_id)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        tag = hashlib.sha256(operation_id.encode()).hexdigest()[:24]
        with locked(self.root / "condor-submit.lock"):
            spec_file = root / "spec.json"
            if spec_file.exists():
                if ExecutionSpec.model_validate_json(spec_file.read_bytes()) != spec:
                    raise ValueError("operation already has a different execution spec")
            else:
                write_ownership(spec_file, spec.model_dump(mode="json"))
            intent = root / "intent.json"
            if not intent.exists():
                write_ownership(intent, {"operation_id": operation_id, "tag": tag})
            receipt = self._receipt(root, request, tag)
            if receipt is None:
                submit_file = root / "job.condor"
                if submit_file.exists():
                    raise RuntimeError(
                        "native submit outcome is unknown; reconcile the durable intent "
                        "with HTCondor before retrying"
                    )
                submit_file = self._submit_file(root, spec, request, tag)
                submitted = self._run(request, "condor_submit", "-terse", str(submit_file))
                if submitted.returncode:
                    raise RuntimeError("condor_submit failed after durable intent")
                match = re.search(r"(?<![0-9])([0-9]+\.[0-9]+)(?![0-9])", submitted.stdout)
                if not match:
                    raise RuntimeError("condor_submit did not return a native job ID")
                receipt = {"job_id": match.group(1), "tag": tag}
                write_ownership(root / "receipt.json", receipt)
        return ExecutionHandle(operation_id, BACKEND, "condor:" + receipt["job_id"], spec.digest())

    def reconcile(self, operation_id: str) -> Reconciliation:
        kind = self._kind(operation_id)
        if kind == "engineering":
            return self.engineering.reconcile(operation_id)
        if kind is None:
            return Reconciliation("not_submitted", reason="durable launch intent absent")
        root = self._path(operation_id)
        spec = ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())
        request = _request(spec)
        intent = json.loads((root / "intent.json").read_text(encoding="utf-8"))
        try:
            receipt = self._receipt(root, request, intent["tag"])
        except (OSError, RuntimeError, ValueError):
            return Reconciliation("unknown", reason="scheduler identity query failed")
        handle = ExecutionHandle(
            operation_id,
            BACKEND,
            "condor:" + receipt["job_id"] if receipt else None,
            spec.digest(),
        )
        return Reconciliation(
            "known" if receipt else "unknown",
            handle,
            None if receipt else "submission intent exists but native job ID is unavailable",
        )

    def _checked(self, handle: ExecutionHandle) -> tuple[Path, ExecutionSpec, Request, str]:
        if handle.backend != BACKEND or self._kind(handle.operation_id) != "native":
            raise ValueError("handle does not belong to a native PostTrainBench job")
        root = self._path(handle.operation_id)
        spec = ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())
        receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
        native = "condor:" + receipt["job_id"]
        if handle.spec_digest != spec.digest() or handle.native_id != native:
            raise ValueError("execution handle/spec mismatch")
        return root, spec, _request(spec), receipt["job_id"]

    @staticmethod
    def _safe_component(value: str) -> str:
        return value.replace("/", "_").replace(":", "_").replace("[", "_").replace("]", "_")

    def _result_path(self, request: Request, job_id: str, tag: str) -> Path:
        gpu = f"_{request.num_gpus}gpu" if request.num_gpus > 1 else ""
        method = (
            f"{request.agent}_{self._safe_component(request.agent_config)}_"
            f"{request.num_hours}h{gpu}_agentinfra_{tag}"
        )
        match = JOB_ID.fullmatch(job_id)
        if match is None:
            raise ValueError("invalid native scheduler job ID")
        run = (
            f"{request.task}_{self._safe_component(request.model_to_train)}_"
            f"{match.group('cluster')}"
        )
        return Path(request.results_root).resolve() / method / run

    def _record(self, request: Request, job_id: str, tag: str) -> dict[str, Any] | None:
        rows = self._query(request, job_id=job_id, tag=tag)
        if len(rows) > 1:
            raise RuntimeError("native scheduler identity is ambiguous")
        return rows[0] if rows else None

    @staticmethod
    def _status(row: dict[str, Any] | None) -> tuple[str, int | None]:
        if row is None:
            return "unknown", None
        status = int(row.get("JobStatus", 0))
        if status in RUNNING:
            return "running", None
        if status == COMPLETED:
            code = int(row.get("ExitCode", 1))
            return ("completed" if code == 0 else "failed"), code
        if status == REMOVED:
            return "cancelled", None
        return "unknown", None

    def _sync_logs(
        self, root: Path, spec: ExecutionSpec, request: Request, job_id: str, tag: str
    ) -> tuple[Path, bool]:
        result = self._result_path(request, job_id, tag)
        sources = (
            root / "scheduler.out",
            root / "scheduler.err",
            result / "output.log",
            result / "error.log",
        )
        offsets_path = root / "log-offsets.json"
        offsets = json.loads(offsets_path.read_text()) if offsets_path.is_file() else {}
        journal = root / "combined.log"
        used = journal.stat().st_size if journal.exists() else 0
        truncated = bool(offsets.get("truncated", False))
        with journal.open("ab") as target:
            for source in sources:
                key = str(source)
                previous = int(offsets.get(key, 0))
                if not source.is_file() or source.is_symlink() or source.stat().st_size < previous:
                    continue
                with source.open("rb") as stream:
                    stream.seek(previous)
                    chunk = stream.read(max(0, spec.max_log_bytes - used))
                    if chunk:
                        header = b"" if previous else f"\n--- {source.name} ---\n".encode()
                        allowance = max(0, spec.max_log_bytes - used)
                        payload = (header + chunk)[:allowance]
                        target.write(payload)
                        used += len(payload)
                    current = stream.tell()
                offsets[key] = current
                if current < source.stat().st_size or used >= spec.max_log_bytes:
                    truncated = True
        offsets["truncated"] = truncated
        _atomic_json(offsets_path, offsets)
        return journal, truncated

    def observe(self, handle: ExecutionHandle, cursor: int = 0) -> ExecutionObservation:
        if self._kind(handle.operation_id) == "engineering":
            return self.engineering.observe(handle, cursor)
        root, spec, request, job_id = self._checked(handle)
        tag = json.loads((root / "intent.json").read_text())["tag"]
        try:
            row = self._record(request, job_id, tag)
            status, exit_code = self._status(row)
        except (OSError, RuntimeError, ValueError):
            status, exit_code = "unknown", None
        log, truncated = self._sync_logs(root, spec, request, job_id, tag)
        size = log.stat().st_size
        if type(cursor) is not int or not 0 <= cursor <= size:
            raise ValueError("invalid raw log cursor")
        with log.open("rb") as stream:
            stream.seek(cursor)
            data = stream.read(65536)
        cleanup = self.cleanup(handle)
        return ExecutionObservation(
            status,
            exit_code,
            data,
            cursor + len(data),
            status not in {"running", "unknown"} and cursor + len(data) == size,
            truncated,
            cleanup,
        )

    def cancel(self, handle: ExecutionHandle) -> CleanupResult:
        if self._kind(handle.operation_id) == "engineering":
            return self.engineering.cancel(handle)
        _, _, request, job_id = self._checked(handle)
        result = self._run(request, "condor_rm", job_id)
        if result.returncode and "not found" not in (result.stderr + result.stdout).lower():
            return CleanupResult(False, "scheduler cancellation failed")
        return self.cleanup(handle)

    def cleanup(self, handle: ExecutionHandle) -> CleanupResult:
        if self._kind(handle.operation_id) == "engineering":
            return self.engineering.cleanup(handle)
        root, _, request, job_id = self._checked(handle)
        tag = json.loads((root / "intent.json").read_text())["tag"]
        try:
            active = self._run(request, "condor_q", job_id, "-json")
            if active.returncode or json.loads(active.stdout or "[]"):
                return CleanupResult(False, "owned scheduler job remains active")
            history = self._run(request, "condor_history", job_id, "-limit", "1", "-json")
            rows = json.loads(history.stdout or "[]") if history.returncode == 0 else []
            if len(rows) != 1 or int(rows[0].get("JobStatus", 0)) not in {REMOVED, COMPLETED}:
                return CleanupResult(False, "scheduler has not confirmed terminal cleanup")
            if self._job_id(rows[0]) != job_id:
                return CleanupResult(False, "scheduler history identity mismatch")
            if json.loads((root / "intent.json").read_text())["tag"] != tag:
                return CleanupResult(False, "operation identity changed")
        except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError):
            return CleanupResult(False, "scheduler cleanup could not be attested")
        return CleanupResult(True, self.cleanup_scope)

    def collect(self, handle: ExecutionHandle) -> Submission:
        if self._kind(handle.operation_id) == "engineering":
            return self.engineering.collect(handle)
        root, spec, request, job_id = self._checked(handle)
        if not self.cleanup(handle).complete:
            raise RuntimeError("cannot collect before scheduler cleanup is confirmed")
        destination = root / "collected"
        if not destination.exists():
            intent = json.loads((root / "intent.json").read_text())
            result = self._result_path(request, job_id, intent["tag"])
            finalize(request, result, Path(spec.workspace))
            with tempfile.TemporaryDirectory(dir=root, prefix=".collect-") as temporary:
                staging = Path(temporary) / "bundle"
                staging.mkdir()
                used = 0
                missing = []
                for name in spec.outputs:
                    source = resolve_material(Path(spec.workspace), name)
                    if not source.exists():
                        missing.append(name)
                        continue
                    candidates = [source] if source.is_file() else list(source.rglob("*"))
                    for item in candidates:
                        if item.is_symlink() or not (item.is_file() or item.is_dir()):
                            raise ValueError("output contains symlink or special file")
                        if item.is_file():
                            used += item.stat().st_size
                    if used > spec.max_artifact_bytes:
                        raise ValueError("evidence exceeds bounded Records artifact budget")
                    target = staging / "outputs" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, target) if source.is_dir() else shutil.copyfile(
                        source, target
                    )
                write_ownership(
                    staging / "execution-receipt.json",
                    {"job_id": job_id, "missing_outputs": missing},
                )
                staging.replace(destination)
        files = tuple(
            path.relative_to(destination).as_posix()
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        )
        receipt = json.loads((destination / "execution-receipt.json").read_text())
        return Submission(
            destination, content_digest(destination), files, tuple(receipt["missing_outputs"])
        )
