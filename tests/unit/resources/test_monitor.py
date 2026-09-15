"""Linux host CPU, memory, and NVIDIA observation tests."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_infra.resources.monitor import LinuxHostResourceMonitor


def _write_proc(proc_root: Path, cpu: str) -> None:
    proc_root.mkdir(exist_ok=True)
    (proc_root / "stat").write_text(f"cpu  {cpu}\n")
    (proc_root / "meminfo").write_text("MemTotal:       32768 kB\nMemAvailable:   24576 kB\n")


def test_samples_cpu_delta_memory_and_gpu_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_proc(tmp_path, "100 0 100 800 0")
    monkeypatch.setattr("agent_infra.resources.monitor.shutil.which", lambda binary: "/nvidia-smi")

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu" in argv:
            stdout = "0, GPU-abc, NVIDIA Test, 24576, 20000, 25\n"
        else:
            stdout = "GPU-abc, 123\n"
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monitor = LinuxHostResourceMonitor(
        node_id="node-a",
        proc_root=tmp_path,
        runner=runner,
        clock=lambda: datetime(2026, 9, 15, tzinfo=UTC),
    )
    first = monitor.sample()
    _write_proc(tmp_path, "150 0 150 900 0")
    second = monitor.sample()

    assert first.cpu_utilization_percent is None
    assert second.cpu_utilization_percent == 50
    assert second.memory_total_bytes == 32768 * 1024
    assert second.memory_available_bytes == 24576 * 1024
    assert second.gpus[0].device_id == "GPU-abc"
    assert second.gpus[0].memory_free_bytes == 20000 * 1024**2
    assert second.gpus[0].compute_process_count == 1


def test_missing_nvidia_tools_degrades_to_an_explicit_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_proc(tmp_path, "100 0 100 800 0")
    monkeypatch.setattr("agent_infra.resources.monitor.shutil.which", lambda binary: None)

    snapshot = LinuxHostResourceMonitor(node_id="cpu-node", proc_root=tmp_path).sample()

    assert snapshot.gpus == ()
    assert "nvidia-smi is unavailable" in snapshot.issues[0]


def test_failed_process_query_is_visible_and_does_not_claim_zero_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_proc(tmp_path, "100 0 100 800 0")
    monkeypatch.setattr("agent_infra.resources.monitor.shutil.which", lambda binary: "/nvidia-smi")

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if "--query-compute-apps=gpu_uuid,pid" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "query failed")
        return subprocess.CompletedProcess(
            argv, 0, "0, GPU-abc, NVIDIA Test, 24576, 20000, 0\n", ""
        )

    snapshot = LinuxHostResourceMonitor(
        node_id="node-a", proc_root=tmp_path, runner=runner
    ).sample()

    assert snapshot.gpus[0].compute_process_count is None
    assert "process query returned a non-zero" in snapshot.issues[0]
