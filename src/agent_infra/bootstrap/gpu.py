"""Conservative NVIDIA admission inventory and explicit local CUDA diagnostics."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from agent_infra.resources.api import HostResourceSnapshot

Command = Callable[..., subprocess.CompletedProcess[str]]
Locator = Callable[[str], str | None]


def gpu_doctor(
    snapshot: HostResourceSnapshot,
    *,
    locate: Locator = shutil.which,
    command: Command = subprocess.run,
) -> dict[str, object]:
    """Read-only check; never configures Docker or starts a container."""
    issues = list(snapshot.issues)
    toolkit = locate("nvidia-ctk") is not None
    if not snapshot.gpus:
        issues.append("no NVIDIA GPUs were discovered by nvidia-smi")
    if not toolkit:
        issues.append("nvidia-ctk is unavailable; install NVIDIA Container Toolkit")
    runtimes: list[str] = []
    cdi_devices: list[str] = []
    if locate("docker") is None:
        issues.append("Docker CLI is unavailable")
    else:
        try:
            response = command(
                ["docker", "info", "--format", "{{json .Runtimes}}"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if response.returncode != 0:
                issues.append("Docker daemon is unavailable to this user")
            else:
                parsed = json.loads(response.stdout)
                if not isinstance(parsed, dict):
                    raise ValueError("invalid Docker runtime list")
                runtimes = sorted(str(name) for name in parsed)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            issues.append(f"Docker runtime check failed: {type(error).__name__}")
    if toolkit:
        try:
            listed = command(
                ["nvidia-ctk", "cdi", "list"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if listed.returncode == 0:
                cdi_devices = sorted(
                    line.strip()
                    for line in listed.stdout.splitlines()
                    if line.strip().startswith("nvidia.com/gpu=")
                )
        except (OSError, subprocess.SubprocessError):
            pass
    observed_cdi = any(f"nvidia.com/gpu={gpu.device_id}" in cdi_devices for gpu in snapshot.gpus)
    if "nvidia" not in runtimes and not observed_cdi:
        issues.append("Docker has neither NVIDIA runtime nor usable NVIDIA CDI devices")
    return {
        "ready": not issues,
        "gpu_devices": [
            {
                "device_id": gpu.device_id,
                "index": gpu.index,
                "name": gpu.name,
                "memory_total_bytes": gpu.memory_total_bytes,
                "memory_free_bytes": gpu.memory_free_bytes,
                "compute_process_count": gpu.compute_process_count,
            }
            for gpu in snapshot.gpus
        ],
        "nvidia_toolkit": toolkit,
        "docker_runtimes": runtimes,
        "cdi_devices": cdi_devices,
        "issues": issues,
    }


def gpu_smoke(
    snapshot: HostResourceSnapshot,
    *,
    device_id: str,
    image: str,
    locate: Locator = shutil.which,
    command: Command = subprocess.run,
) -> dict[str, object]:
    """Run one bounded CUDA matrix calculation in an already-local PyTorch image."""
    diagnosis = gpu_doctor(snapshot, locate=locate, command=command)
    if not diagnosis["ready"]:
        return diagnosis | {"smoke": "not_run"}
    observed = {gpu.device_id: gpu for gpu in snapshot.gpus}
    if device_id not in observed:
        raise ValueError("smoke GPU UUID is not present in the host snapshot")
    if observed[device_id].compute_process_count != 0:
        raise ValueError("smoke GPU has active or unknown compute processes")
    if observed[device_id].memory_free_bytes < 1024**3:
        raise ValueError("smoke GPU has less than 1 GiB free memory")
    if not image or image.startswith("-"):
        raise ValueError("supply an existing local Python image")
    try:
        inspected = command(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Python image inspection failed: {type(error).__name__}") from error
    image_id = inspected.stdout.strip()
    if inspected.returncode != 0 or not image_id.startswith("sha256:"):
        raise ValueError("Python image is not available locally; no image was pulled")
    name = "agent-infra-gpu-smoke-" + uuid.uuid4().hex[:12]
    script = Path(__file__).with_name("cuda_probe.py").read_text(encoding="utf-8")
    cdi_devices = diagnosis["cdi_devices"]
    cdi = isinstance(cdi_devices, list) and f"nvidia.com/gpu={device_id}" in cdi_devices
    try:
        result = command(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--pull=never",
                "--network=none",
                "--cpus=1",
                "--memory=2g",
                "--pids-limit=128",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,nosuid,size=128m",
                "--device" if cdi else "--gpus",
                f"nvidia.com/gpu={device_id}" if cdi else f'"device={device_id}"',
                "--entrypoint",
                "python",
                image_id,
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        passed = result.returncode == 0 and "CUDA computation passed" in result.stdout
        return {
            "ready": passed,
            "smoke": "passed" if passed else "failed",
            "device_id": device_id,
            "image_id": image_id,
            "evidence": result.stdout.strip()[-500:] if passed else "",
            "issues": [] if passed else [result.stderr.strip()[-500:] or "CUDA smoke failed"],
        }
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "ready": False,
            "smoke": "failed",
            "issues": [f"CUDA smoke execution failed: {type(error).__name__}"],
        }
    finally:
        # Only the unique container created by this smoke may be removed.
        try:
            command(
                ["docker", "rm", "-f", name], capture_output=True, text=True, timeout=8, check=False
            )
        except (OSError, subprocess.SubprocessError):
            pass
