"""Single-node Docker runtime. Each handle owns exactly one disposable container."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from agent_infra.contracts.files import content_digest, relative_path, resolve_material
from agent_infra.environments.api import (
    CleanupResult,
    EnvironmentHandle,
    LogCursor,
    Observation,
    ProcessCommand,
    SandboxSpec,
    Submission,
)
from agent_infra.environments.recovery import write_ownership


@dataclass
class _Instance:
    spec: SandboxSpec
    name: str
    image_id: str
    log_dir: Path
    command: ProcessCommand | None = None
    process: subprocess.Popen[bytes] | None = None
    threads: list[threading.Thread] = field(default_factory=list)
    started_at: float = 0
    terminal: str | None = None
    exit_code: int | None = None
    removed: bool = False
    truncated: bool = False


class DockerEnvironment:
    def __init__(
        self,
        state_dir: Path,
        *,
        artifact_limit_bytes: int = 1024**3,
        log_limit_bytes: int = 8 * 1024**2,
    ) -> None:
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._owner = uuid.uuid4().hex
        self._instances: dict[str, _Instance] = {}
        self._keys: dict[str, EnvironmentHandle] = {}
        self._lock = threading.RLock()
        self._artifact_limit = artifact_limit_bytes
        self._log_limit = log_limit_bytes

    def _docker(self, args: list[str]) -> str:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError(f"Docker {args[0]} failed (controller logs required)")
        return result.stdout

    def _get(self, handle: EnvironmentHandle) -> _Instance:
        try:
            return self._instances[handle.id]
        except KeyError as error:
            raise ValueError("unknown environment handle") from error

    def prepare(self, spec: SandboxSpec) -> EnvironmentHandle:
        with self._lock:
            if spec.key in self._keys:
                handle = self._keys[spec.key]
                if self._get(handle).spec != spec:
                    raise ValueError("environment key already has a different specification")
                return handle
            if spec.phase not in {"solver", "submission", "scorer"} or not spec.key.strip():
                raise ValueError("invalid environment identity")
            if (
                not math.isfinite(spec.cpu_cores)
                or spec.cpu_cores <= 0
                or spec.memory_bytes < 6 * 1024**2
            ):
                raise ValueError("invalid CPU/memory limits")
            if spec.workspace.is_symlink() or not spec.workspace.is_dir():
                raise ValueError("workspace must be a regular directory")
            for path in (
                str(spec.workspace.resolve()),
                spec.home_target,
                *(str(m.source.resolve()) for m in spec.readonly_inputs),
                *(m.target for m in spec.readonly_inputs),
            ):
                if any(char in path for char in (",", "\n", "\0")):
                    raise ValueError("unsupported mount path characters")
            content_digest(spec.workspace)
            targets = [PurePosixPath("/workspace"), PurePosixPath("/tmp")]
            # /workspace children are allowed as readonly overlays.
            seen: list[PurePosixPath] = []
            for mount in spec.readonly_inputs:
                target = PurePosixPath(mount.target)
                if (
                    not target.is_absolute()
                    or ".." in target.parts
                    or target in targets
                    or target == PurePosixPath("/")
                ):
                    raise ValueError("invalid input mount target")
                if not (
                    target.is_relative_to("/workspace")
                    or target.is_relative_to("/inputs")
                    or target == PurePosixPath("/submission")
                ):
                    raise ValueError(
                        "input target must be under /workspace, /inputs or /submission"
                    )
                if any(target.is_relative_to(old) or old.is_relative_to(target) for old in seen):
                    raise ValueError("overlapping readonly mounts")
                seen.append(target)
                content_digest(mount.source)
            if spec.phase != "solver" and (spec.private_home is not None or spec.network):
                raise ValueError("evaluation phases cannot inherit Agent credentials or network")
            if spec.private_home is not None:
                if spec.private_home.is_symlink() or not spec.private_home.is_dir():
                    raise ValueError("private home must be a regular directory")
                if "," in str(
                    spec.private_home.resolve()
                ) or spec.private_home.resolve().is_relative_to(spec.workspace.resolve()):
                    raise ValueError("private home must be separate from workspace")
                content_digest(spec.private_home)
                if (
                    not PurePosixPath(spec.home_target).is_relative_to("/home/agent")
                    or ".." in PurePosixPath(spec.home_target).parts
                ):
                    raise ValueError("invalid private home target")
            explicit_host = os.environ.get("DOCKER_HOST")
            context = json.loads(self._docker(["context", "inspect"]))[0]
            endpoint = context["Endpoints"]["docker"]["Host"]
            if not os.environ.get("DOCKER_CONTEXT"):
                endpoint = explicit_host or endpoint
            if not endpoint.startswith("unix://"):
                raise ValueError("local runtime requires a local Unix Docker endpoint")
            image = json.loads(self._docker(["image", "inspect", spec.image]))[0]
            if image["Config"].get("Volumes"):
                raise ValueError("images declaring implicit volumes are not supported")
            handle = EnvironmentHandle(uuid.uuid4().hex)
            log_dir = self.state_dir / handle.id
            log_dir.mkdir(mode=0o700)
            name = f"agent-infra-{self._owner[:12]}-{handle.id[:12]}"
            self._instances[handle.id] = _Instance(spec, name, image["Id"], log_dir)
            self._keys[spec.key] = handle
            self._journal(self._instances[handle.id], "prepared")
            return handle

    def _journal(self, item: _Instance, lifecycle: str) -> None:
        write_ownership(
            item.log_dir / "ownership.json",
            {
                "owner": self._owner,
                "name": item.name,
                "key": item.spec.key,
                "image_id": item.image_id,
                "lifecycle": lifecycle,
            },
        )

    def _inspect(self, instance: _Instance) -> dict[str, Any] | None:
        ids = self._docker(
            ["container", "ls", "-a", "--filter", f"name=^/{instance.name}$", "--format", "{{.ID}}"]
        )
        if not ids.strip():
            return None
        info: dict[str, Any] = json.loads(self._docker(["inspect", instance.name]))[0]
        if info["Config"].get("Labels", {}).get("agent-infra.owner") != self._owner:
            raise RuntimeError("container ownership mismatch")
        return info

    def start(self, handle: EnvironmentHandle, command: ProcessCommand) -> None:
        with self._lock:
            item = self._get(handle)
            if item.command is not None:
                if item.command != command:
                    raise ValueError("environment already started with another command")
                return
            if item.removed:
                raise ValueError("environment was already cleaned")
            if not command.argv or any(
                not isinstance(arg, str) or "\0" in arg for arg in command.argv
            ):
                raise ValueError("invalid process argv")
            if not math.isfinite(command.timeout_seconds) or command.timeout_seconds <= 0:
                raise ValueError("timeout must be finite and positive")
            if (
                not PurePosixPath(command.cwd).is_relative_to("/workspace")
                or ".." in PurePosixPath(command.cwd).parts
            ):
                raise ValueError("command cwd must stay under /workspace")
            spec = item.spec
            args = [
                "create",
                "-i",
                "--name",
                item.name,
                "--label",
                f"agent-infra.owner={self._owner}",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--user",
                f"{os.getuid() or 65534}:{os.getgid() or 65534}",
                "--cpus",
                str(spec.cpu_cores),
                "--memory",
                str(spec.memory_bytes),
                "--memory-swap",
                str(spec.memory_bytes),
                "--pids-limit",
                "128",
                "--network",
                "bridge" if spec.network else "none",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
                "--tmpfs",
                "/home/agent:rw,nosuid,nodev,size=67108864,mode=1777",
                "--log-driver",
                "local",
                "--log-opt",
                "max-size=10m",
                "--log-opt",
                "max-file=1",
                "--log-opt",
                "compress=false",
                "--workdir",
                command.cwd,
                "--env",
                "HOME=/home/agent",
                "--mount",
                f"type=bind,src={spec.workspace.resolve()},dst=/workspace",
            ]
            for mount in spec.readonly_inputs:
                args += [
                    "--mount",
                    f"type=bind,src={mount.source.resolve()},dst={mount.target},readonly",
                ]
            if spec.private_home is not None:
                args += [
                    "--mount",
                    f"type=bind,src={spec.private_home.resolve()},dst={spec.home_target}",
                ]
            if spec.gpu_device_ids:
                args += ["--gpus", '"device=' + ",".join(spec.gpu_device_ids) + '"']
            for key, value in command.environment:
                if not key or "=" in key or "\0" in key + value:
                    raise ValueError("invalid environment variable")
                args += ["--env", f"{key}={value}"]
            # Override image ENTRYPOINT; the approved command is the complete executable.
            args += ["--entrypoint", command.argv[0], item.image_id, *command.argv[1:]]
            item.command = command
            try:
                self._journal(item, "creating")
                self._docker(args)
                self._journal(item, "created")
                info = self._inspect(item)
                if info is None:
                    raise RuntimeError("created container disappeared")
                limits = info["HostConfig"]
                if limits["Memory"] != spec.memory_bytes or limits["NanoCpus"] != int(
                    spec.cpu_cores * 1e9
                ):
                    raise RuntimeError("container resource limits do not match lease")
                allocated = tuple(
                    device
                    for req in (limits.get("DeviceRequests") or [])
                    for device in (req.get("DeviceIDs") or [])
                )
                if set(allocated) != set(spec.gpu_device_ids):
                    raise RuntimeError("container GPU mapping does not match lease")
                item.started_at = time.monotonic()
                item.process = subprocess.Popen(
                    ["docker", "start", "--attach", "--interactive", item.name],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert item.process.stdout is not None and item.process.stderr is not None
                for stream, filename in (
                    (item.process.stdout, "stdout"),
                    (item.process.stderr, "stderr"),
                ):
                    thread = threading.Thread(
                        target=self._drain, args=(item, stream, filename), daemon=True
                    )
                    thread.start()
                    item.threads.append(thread)
                thread = threading.Thread(target=self._write_stdin, args=(item,), daemon=True)
                thread.start()
                item.threads.append(thread)
            except BaseException:
                item.terminal = "failed"
                raise

    def _write_stdin(self, item: _Instance) -> None:
        assert (
            item.process is not None and item.process.stdin is not None and item.command is not None
        )
        try:
            item.process.stdin.write((item.command.stdin_text or "").encode())
            item.process.stdin.close()
        except (OSError, ValueError):
            pass

    def _drain(self, item: _Instance, stream: BinaryIO, filename: str) -> None:
        written = 0
        with stream, (item.log_dir / filename).open("wb") as target:
            while chunk := os.read(stream.fileno(), 4096):
                keep = chunk[: max(0, self._log_limit - written)]
                target.write(keep)
                target.flush()
                written += len(keep)
                if len(keep) < len(chunk):
                    item.truncated = True

    def observe(self, handle: EnvironmentHandle, cursor: LogCursor | None = None) -> Observation:
        with self._lock:
            item = self._get(handle)
            cursor = cursor or LogCursor()
            if min(cursor.stdout, cursor.stderr) < 0:
                raise ValueError("negative log cursor")
            if item.command is None:
                status = "prepared"
            elif item.removed:
                status = item.terminal or "failed"
            else:
                info = self._inspect(item)
                if info is None:
                    item.terminal = item.terminal or "failed"
                elif info["State"]["Running"]:
                    if time.monotonic() - item.started_at > item.command.timeout_seconds:
                        result = self.cancel(handle)
                        if result.complete:
                            item.terminal = "timed_out"
                elif (
                    info["State"]["Status"] == "created"
                    and item.process is not None
                    and item.process.poll() is None
                ):
                    if time.monotonic() - item.started_at > item.command.timeout_seconds:
                        self.cleanup(handle)
                        item.terminal = "timed_out"
                elif info["State"]["Status"] == "created":
                    item.terminal = "failed"
                else:
                    item.exit_code = info["State"]["ExitCode"]
                    item.terminal = item.terminal or (
                        "oom" if info["State"].get("OOMKilled") else "exited"
                    )
                status = item.terminal or "running"
            if status not in {"running", "prepared"}:
                for thread in item.threads:
                    thread.join(timeout=1)
            chunks = []
            positions = []
            for name, position in (("stdout", cursor.stdout), ("stderr", cursor.stderr)):
                path = item.log_dir / name
                if path.exists():
                    with path.open("rb") as source:
                        source.seek(position)
                        chunk = source.read(65536)
                    positions.append(position + len(chunk))
                    chunks.append(chunk.decode("utf-8", errors="replace"))
                else:
                    positions.append(position)
                    chunks.append("")
            return Observation(
                status, item.exit_code, chunks[0], chunks[1], LogCursor(*positions), item.truncated
            )

    def cancel(self, handle: EnvironmentHandle) -> CleanupResult:
        with self._lock:
            item = self._get(handle)
            try:
                info = self._inspect(item)
                if info is not None and info["State"]["Running"]:
                    self._docker(["kill", item.name])
                info = self._inspect(item)
                complete = info is None or not info["State"]["Running"]
                if complete:
                    item.terminal = item.terminal or "cancelled"
                return CleanupResult(complete)
            except (RuntimeError, OSError, subprocess.SubprocessError):
                return CleanupResult(False, "container stop could not be verified")

    def execute_control(self, handle: EnvironmentHandle, argv: tuple[str, ...], stdin: str) -> str:
        """Internal runtime control transport; never exposed as arbitrary host execution."""
        with self._lock:
            item = self._get(handle)
            info = self._inspect(item)
            if info is None or not info["State"]["Running"]:
                raise RuntimeError("research container is not running")
            result = subprocess.run(
                ["docker", "exec", "-i", item.name, *argv],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode:
                raise RuntimeError(
                    "research runtime unavailable; check Python 3 image and container"
                )
            return result.stdout

    def cleanup(self, handle: EnvironmentHandle) -> CleanupResult:
        with self._lock:
            item = self._get(handle)
            try:
                existing = self._inspect(item)
                if (
                    existing is None
                    and json.loads((item.log_dir / "ownership.json").read_text()).get("lifecycle")
                    == "creating"
                ):
                    return CleanupResult(
                        False, "unacknowledged Docker create; cleanup is uncertain"
                    )
                if existing is not None:
                    self._docker(["rm", "--force", item.name])
                if self._inspect(item) is not None:
                    return CleanupResult(False, "container still exists")
                item.removed = True
                if item.process is not None:
                    item.process.wait(timeout=5)
                self._journal(item, "removed")
                return CleanupResult(True)
            except (RuntimeError, OSError, subprocess.SubprocessError):
                return CleanupResult(False, "container removal could not be verified")

    def collect_workspace(self, handle: EnvironmentHandle, destination: Path) -> Submission:
        with self._lock:
            workspace = self._get(handle).spec.workspace
            return self.collect(
                handle, tuple(p.name for p in sorted(workspace.iterdir())), destination
            )

    def collect(
        self, handle: EnvironmentHandle, paths: tuple[str, ...], destination: Path
    ) -> Submission:
        with self._lock:
            item = self._get(handle)
            if not item.removed or self._inspect(item) is not None:
                raise ValueError("container must be removed before collecting submission")
            if destination.resolve().is_relative_to(item.spec.workspace.resolve()):
                raise ValueError("submission destination must be outside workspace")
            if destination.exists() or destination.is_symlink():
                raise FileExistsError("submission destination already exists")
            sources: list[tuple[str, Path]] = []
            missing: list[str] = []
            total = 0
            selected: list[PurePosixPath] = []
            for value in paths:
                relative = relative_path(value)
                if any(
                    relative.is_relative_to(old) or old.is_relative_to(relative) for old in selected
                ):
                    raise ValueError("overlapping output paths")
                selected.append(relative)
                source = resolve_material(item.spec.workspace, value)
                if not source.exists():
                    missing.append(value)
                    continue
                content_digest(source)  # Reject symlinks/FIFOs before copy.
                files = [source] if source.is_file() else list(source.rglob("*"))
                total += sum(file.stat().st_size for file in files if file.is_file())
                if total > self._artifact_limit:
                    raise ValueError("submission exceeds artifact size limit")
                sources.append((value, source))
            destination.mkdir(parents=True, mode=0o700)
            for value, source in sources:
                target = destination / value
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copyfile(source, target)
            digest = content_digest(destination)
            files_out = tuple(
                sorted(
                    path.relative_to(destination).as_posix()
                    for path in destination.rglob("*")
                    if path.is_file()
                )
            )
            for path in destination.rglob("*"):
                path.chmod(0o555 if path.is_dir() else 0o444)
            # Parent remains controller-writable; only read-only mounts reach later phases.
            return Submission(destination.resolve(), digest, files_out, tuple(missing))
