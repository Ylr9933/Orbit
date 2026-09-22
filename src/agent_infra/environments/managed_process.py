"""Recoverable, at-most-once launch of cooperative local processes on Linux."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agent_infra.contracts.files import content_digest, resolve_material
from agent_infra.environments._process_state import boot_id, locked, process_identity
from agent_infra.environments.api import CleanupResult, Submission
from agent_infra.environments.execution_api import (
    ExecutionHandle,
    ExecutionObservation,
    ExecutionSpec,
    Reconciliation,
)
from agent_infra.environments.recovery import write_ownership


class ManagedProcessBackend:
    backend_id = "managed-process-v1"
    cleanup_scope = "process_group"
    features: tuple[str, ...] = (
        "durable_operation",
        "bounded_logs",
        "process_group_cleanup",
        "wall_timeout",
    )

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError("managed process state must be a private directory")
        self._children: list[subprocess.Popen[bytes]] = []

    def _path(self, operation_id: str) -> Path:
        if not operation_id or len(operation_id) > 200:
            raise ValueError("invalid backend operation ID")
        path = self.root / hashlib.sha256(operation_id.encode()).hexdigest()
        if path.is_symlink():
            raise ValueError("unsafe operation directory")
        return path

    def _reap(self) -> None:
        self._children = [child for child in self._children if child.poll() is None]

    def submit(self, operation_id: str, spec: ExecutionSpec) -> ExecutionHandle:
        spec = ExecutionSpec.model_validate_json(spec.model_dump_json())
        root = self._path(operation_id)
        with locked(self.root / "launch.lock"):
            self._reap()
            root.mkdir(exist_ok=True, mode=0o700)
            spec_file = root / "spec.json"
            if spec_file.exists():
                existing = ExecutionSpec.model_validate_json(spec_file.read_bytes())
                if existing != spec:
                    raise ValueError("operation already has a different execution spec")
            else:
                write_ownership(spec_file, spec.model_dump(mode="json"))
            # Intent is fsynced BEFORE Popen. Absence of an acknowledgement never authorizes replay.
            if not (root / "launch.json").exists():
                Path(spec.workspace).mkdir(parents=True, exist_ok=True, mode=0o700)
                write_ownership(root / "launch.json", {"operation_id": operation_id})
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "agent_infra.environments._process_supervisor",
                        str(root),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )
                self._children.append(child)
            handle = self.reconcile(operation_id).handle
            assert handle is not None
            return handle

    def reconcile(self, operation_id: str) -> Reconciliation:
        self._reap()
        root = self._path(operation_id)
        if not (root / "launch.json").exists():
            return Reconciliation("not_submitted", reason="durable launch intent absent")
        spec = ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())
        owner: dict[str, Any] | None = None
        if (root / "owner.json").exists():
            owner = json.loads((root / "owner.json").read_text())
        native_id = f"{owner['boot']}:{owner['pid']}:{owner['start']}" if owner else None
        handle = ExecutionHandle(operation_id, self.backend_id, native_id, spec.digest())
        if (root / "result.json").exists():
            return Reconciliation("known", handle)
        if owner and owner["boot"] == boot_id():
            pid = int(owner["pid"])
            if process_identity(pid) == (owner["start"], pid, pid):
                return Reconciliation("known", handle)
        return Reconciliation(
            "unknown", handle, "launch pending or supervisor identity unavailable"
        )

    def _checked(self, handle: ExecutionHandle) -> Path:
        if handle.backend != self.backend_id:
            raise ValueError("handle belongs to a different backend")
        current = self.reconcile(handle.operation_id).handle
        if current is None or current.spec_digest != handle.spec_digest:
            raise ValueError("execution handle/spec mismatch")
        if handle.native_id is not None and handle.native_id != current.native_id:
            raise ValueError("native identity changed; refusing operation")
        return self._path(handle.operation_id)

    def spec(self, handle: ExecutionHandle) -> ExecutionSpec:
        """Read a verified persisted spec for backend extensions; do not expose mutation."""
        root = self._checked(handle)
        return ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())

    def observe(self, handle: ExecutionHandle, cursor: int = 0) -> ExecutionObservation:
        root = self._checked(handle)
        reconciliation = self.reconcile(handle.operation_id)
        result: dict[str, Any] = {}
        if (root / "result.json").exists():
            result = json.loads((root / "result.json").read_text())
        path = root / "combined.log"
        size = path.stat().st_size if path.exists() else 0
        if type(cursor) is not int or not 0 <= cursor <= size:
            raise ValueError("invalid raw log cursor")
        data = b""
        if path.exists():
            with path.open("rb") as stream:
                stream.seek(cursor)
                data = stream.read(65536)
        return ExecutionObservation(
            result.get("status", "running" if reconciliation.state == "known" else "unknown"),
            result.get("exit_code"),
            data,
            cursor + len(data),
            bool(result) and cursor + len(data) == size,
            bool(result.get("logs_truncated", False)),
            self.cleanup(handle),
        )

    def cancel(self, handle: ExecutionHandle) -> CleanupResult:
        root = self._checked(handle)
        # No PID-directed signaling here. Only the verified live supervisor signals its children.
        with locked(self.root / "launch.lock"):
            write_ownership(root / "cancel.json", {"requested": True})
        return self.cleanup(handle)

    def cleanup(self, handle: ExecutionHandle) -> CleanupResult:
        root = self._checked(handle)
        if (root / "result.json").exists():
            result = json.loads((root / "result.json").read_text())
            owner = json.loads((root / "owner.json").read_text())
            pid = int(owner["pid"])
            if owner["boot"] == boot_id() and process_identity(pid) == (owner["start"], pid, pid):
                return CleanupResult(False, "supervisor is still closing its journal")
            return CleanupResult(bool(result["cleanup_complete"]), "scope: owned process group")
        return CleanupResult(False, "supervisor has not confirmed process-group cleanup")

    def collect(self, handle: ExecutionHandle) -> Submission:
        root = self._checked(handle)
        if not self.cleanup(handle).complete:
            raise RuntimeError("cannot freeze outputs until process-group cleanup is confirmed")
        spec = ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())
        destination = root / "collected"
        if not destination.exists():
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
                    if not (source.is_file() or source.is_dir()):
                        raise ValueError("output must be a regular file or directory")
                    # Validate descendants before copy; only bounded regular files are accepted.
                    candidates = [source] if source.is_file() else list(source.rglob("*"))
                    for item in candidates:
                        if item.is_symlink() or not (item.is_file() or item.is_dir()):
                            raise ValueError("output contains symlink or special file")
                        if item.is_file():
                            used += item.stat().st_size
                    if used > spec.max_artifact_bytes:
                        raise ValueError("declared outputs exceed collection budget")
                    target = staging / "outputs" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copyfile(source, target)
                result = json.loads((root / "result.json").read_text())
                (staging / "execution-receipt.json").write_text(
                    json.dumps(result | {"missing_outputs": missing})
                )
                for item in staging.rglob("*"):
                    if item.is_file():
                        with item.open("rb") as stream:
                            os.fsync(stream.fileno())
                staging.replace(destination)
                descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        files = tuple(
            p.relative_to(destination).as_posix()
            for p in sorted(destination.rglob("*"))
            if p.is_file()
        )
        receipt = json.loads((destination / "execution-receipt.json").read_text())
        return Submission(
            destination, content_digest(destination), files, tuple(receipt["missing_outputs"])
        )
