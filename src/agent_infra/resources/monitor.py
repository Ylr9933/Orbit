"""Read-only Linux and NVIDIA host resource observation."""

from __future__ import annotations

import csv
import os
import shutil
import socket
import subprocess
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from agent_infra.resources.api import GpuObservation, HostResourceSnapshot

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
Clock = Callable[[], datetime]


def _run_command(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )


class LinuxHostResourceMonitor:
    """Collect snapshots; CPU utilization becomes available after two samples."""

    def __init__(
        self,
        *,
        node_id: str | None = None,
        proc_root: Path = Path("/proc"),
        runner: CommandRunner = _run_command,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._node_id = node_id or socket.gethostname()
        self._proc_root = proc_root
        self._runner = runner
        self._clock = clock
        self._previous_cpu: tuple[int, int] | None = None
        self._lock = threading.Lock()

    def sample(self) -> HostResourceSnapshot:
        with self._lock:
            cpu_utilization = self._read_cpu_utilization()
        memory_total, memory_available = self._read_memory()
        gpus, gpu_issues = self._read_gpus()
        try:
            load_average = os.getloadavg()[0]
        except OSError:
            load_average = None
        return HostResourceSnapshot(
            node_id=self._node_id,
            captured_at=self._clock(),
            cpu_logical_cores=os.cpu_count() or 1,
            cpu_utilization_percent=cpu_utilization,
            load_average_1m=load_average,
            memory_total_bytes=memory_total,
            memory_available_bytes=memory_available,
            gpus=gpus,
            issues=gpu_issues,
        )

    def _read_cpu_utilization(self) -> float | None:
        first_line = (self._proc_root / "stat").read_text(encoding="utf-8").splitlines()[0]
        values = [int(value) for value in first_line.split()[1:]]
        if len(values) < 4:
            raise ValueError("/proc/stat CPU line is incomplete")
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        non_idle = sum(values[:3]) + sum(values[5:8])
        total = idle + non_idle
        current = (total, idle)
        previous = self._previous_cpu
        self._previous_cpu = current
        if previous is None:
            return None
        total_delta = total - previous[0]
        idle_delta = idle - previous[1]
        if total_delta <= 0:
            return None
        return round(100 * (1 - idle_delta / total_delta), 2)

    def _read_memory(self) -> tuple[int, int]:
        values: dict[str, int] = {}
        for line in (self._proc_root / "meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", maxsplit=1)
            number = raw.strip().split()[0]
            values[key] = int(number) * 1024
        try:
            return values["MemTotal"], values["MemAvailable"]
        except KeyError as error:
            raise ValueError("/proc/meminfo lacks total or available memory") from error

    def _read_gpus(self) -> tuple[tuple[GpuObservation, ...], tuple[str, ...]]:
        executable = shutil.which("nvidia-smi")
        if executable is None:
            return (), ("nvidia-smi is unavailable; NVIDIA GPU metrics were not collected.",)
        try:
            result = self._runner(
                [
                    executable,
                    "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ]
            )
        except (OSError, subprocess.SubprocessError) as error:
            return (), (f"NVIDIA GPU query failed: {type(error).__name__}.",)
        if result.returncode != 0:
            return (), ("NVIDIA GPU query returned a non-zero exit status.",)
        process_counts, process_issue = self._read_gpu_process_counts(executable)
        observations: list[GpuObservation] = []
        try:
            rows = csv.reader(result.stdout.splitlines(), skipinitialspace=True)
            for row in rows:
                if not row:
                    continue
                index, device_id, name, total_mib, free_mib, utilization = row
                observations.append(
                    GpuObservation(
                        device_id=device_id.strip(),
                        index=int(index),
                        name=name.strip(),
                        memory_total_bytes=int(total_mib) * 1024**2,
                        memory_free_bytes=int(free_mib) * 1024**2,
                        utilization_percent=float(utilization),
                        compute_process_count=(
                            process_counts.get(device_id.strip(), 0)
                            if process_counts is not None
                            else None
                        ),
                    )
                )
        except (TypeError, ValueError) as error:
            return (), (f"Unable to parse NVIDIA GPU metrics: {type(error).__name__}.",)
        return tuple(observations), ((process_issue,) if process_issue else ())

    def _read_gpu_process_counts(self, executable: str) -> tuple[dict[str, int] | None, str | None]:
        try:
            result = self._runner(
                [
                    executable,
                    "--query-compute-apps=gpu_uuid,pid",
                    "--format=csv,noheader,nounits",
                ]
            )
        except (OSError, subprocess.SubprocessError) as error:
            return None, f"NVIDIA process query failed: {type(error).__name__}."
        if result.returncode != 0:
            return None, "NVIDIA process query returned a non-zero exit status."
        counts: dict[str, int] = {}
        for row in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
            if len(row) == 2:
                device_id = row[0].strip()
                counts[device_id] = counts.get(device_id, 0) + 1
        return counts, None
