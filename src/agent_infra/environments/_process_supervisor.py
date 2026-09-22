"""Detached supervisor for trusted cooperative processes; not an agent sandbox.

Journal own session identity before forking a command. Never relaunch an operation.
Only this live group leader signals group members, with PID identity checks.
"""

import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

from agent_infra.contracts.files import resolve_material
from agent_infra.environments._process_state import (
    boot_id,
    group_members,
    locked,
    process_identity,
    signal_members,
)
from agent_infra.environments.execution_api import ExecutionSpec
from agent_infra.environments.recovery import write_ownership


def supervise(root: Path) -> None:
    with locked(root / "supervisor.lock", blocking=False):
        if (root / "owner.json").exists() or (root / "result.json").exists():
            return
        spec = ExecutionSpec.model_validate_json((root / "spec.json").read_bytes())
        pid = os.getpid()
        identity = process_identity(pid)
        if identity is None or identity[1:] != (pid, pid):
            raise RuntimeError("supervisor must own its process group and session")
        started = time.monotonic()
        write_ownership(
            root / "owner.json",
            {"pid": pid, "start": identity[0], "boot": boot_id(), "started": started},
        )
        process: subprocess.Popen[bytes] | None = None
        status, exit_code, truncated = "failed", None, False
        unclosed_pipe = False
        try:
            if (root / "cancel.json").exists():
                status = "cancelled"
                return
            workspace = Path(spec.workspace)
            cwd = (
                workspace
                if spec.command.cwd == "."
                else resolve_material(workspace, spec.command.cwd)
            )
            if not cwd.is_dir():
                raise ValueError("command cwd does not exist inside the owned workspace")
            environment = {
                "PATH": os.defpath,
                "LANG": "C.UTF-8",
                "HOME": str(workspace),
                "PYTHONUNBUFFERED": "1",
            }
            process = subprocess.Popen(
                spec.command.argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            status = "running"
            assert process.stdout is not None
            count, stop_at, exit_at = 0, None, None
            with process.stdout as stream, selectors.DefaultSelector() as selector:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
                with (root / "combined.log").open("wb") as output:
                    while True:
                        now = time.monotonic()
                        if stop_at is None and (
                            (root / "cancel.json").exists()
                            or now - started >= spec.command.timeout_seconds
                        ):
                            status = "cancelled" if (root / "cancel.json").exists() else "timed_out"
                            stop_at = now
                            signal_members(pid, signal.SIGTERM)
                        if stop_at is not None and now - stop_at >= spec.cancellation_grace_seconds:
                            signal_members(pid, signal.SIGKILL)
                        exited = process.poll() is not None
                        if exited:
                            if exit_at is None:
                                exit_at = now
                            signal_members(pid, signal.SIGKILL)
                        for key, _ in selector.select(0.05):
                            data = os.read(key.fd, 65536)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            kept = data[: max(0, spec.max_log_bytes - count)]
                            output.write(kept)
                            output.flush()
                            count += len(kept)
                            truncated |= len(data) != len(kept)
                        if exited and not selector.get_map():
                            break
                        if (exit_at is not None and now - exit_at > 2) or (
                            stop_at is not None
                            and now - stop_at > spec.cancellation_grace_seconds + 3
                        ):
                            unclosed_pipe, truncated = True, True
                            break
                    output.flush()
                    os.fsync(output.fileno())
            exit_code = process.poll()
            if status == "running":
                status = "completed" if exit_code == 0 else "failed"
        except Exception as error:
            truncated = True
            write_ownership(root / "error.json", {"error": type(error).__name__})
        finally:
            deadline = time.monotonic() + 2
            while group_members(pid) and time.monotonic() < deadline:
                signal_members(pid, signal.SIGKILL)
                time.sleep(0.02)
            if process is not None:
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            write_ownership(
                root / "result.json",
                {
                    "status": status if status != "running" else "failed",
                    "exit_code": exit_code,
                    "logs_truncated": truncated,
                    "cleanup_complete": not unclosed_pipe and not group_members(pid),
                    "scope": "process_group",
                    "elapsed_seconds": time.monotonic() - started,
                },
            )


if __name__ == "__main__":
    supervise(Path(sys.argv[1]))
