"""GPU authorization and bounded diagnostic commands without touching Docker."""

import subprocess
from datetime import UTC, datetime

import pytest

from agent_infra.bootstrap.gpu import gpu_doctor, gpu_smoke
from agent_infra.resources import GpuObservation, HostResourceSnapshot
from agent_infra.resources.gpu import authorized_gpus

GIB = 1024**3


def snapshot(*, processes: int = 0, free: int = 20 * GIB) -> HostResourceSnapshot:
    return HostResourceSnapshot(
        "local",
        datetime.now(UTC),
        8,
        0,
        0,
        32 * GIB,
        24 * GIB,
        (GpuObservation("GPU-one", 0, "Test GPU", 24 * GIB, free, 0, processes),),
    )


def test_authorization_only_maps_explicit_observed_uuids() -> None:
    assert authorized_gpus(snapshot(), ()) == ()
    assert [gpu.device_id for gpu in authorized_gpus(snapshot(), ("GPU-one",))] == ["GPU-one"]
    with pytest.raises(ValueError, match="duplicate"):
        authorized_gpus(snapshot(), ("GPU-one", "GPU-one"))
    with pytest.raises(ValueError, match="not present"):
        authorized_gpus(snapshot(), ("GPU-other",))


def test_doctor_reports_missing_runtime_without_mutation() -> None:
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"runc":{}}', "")

    result = gpu_doctor(snapshot(), locate=lambda name: "/bin/" + name, command=command)
    assert result["ready"] is False
    assert result["gpu_devices"][0]["device_id"] == "GPU-one"
    assert any("no nvidia runtime" in issue for issue in result["issues"])
    assert calls == [["docker", "info", "--format", "{{json .Runtimes}}"]]


def test_smoke_uses_one_uuid_local_image_and_own_cleanup() -> None:
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, '{"nvidia":{}}', "")
        if argv[1] == "image":
            return subprocess.CompletedProcess(argv, 0, "sha256:abc\n", "")
        if argv[1] == "run":
            return subprocess.CompletedProcess(argv, 0, "cuda_ok Test GPU True\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = gpu_smoke(
        snapshot(),
        device_id="GPU-one",
        image="local:cuda",
        locate=lambda _: "/bin/tool",
        command=command,
    )
    assert result["smoke"] == "passed"
    run = calls[2]
    assert run[run.index("--gpus") + 1] == '"device=GPU-one"'
    assert run[run.index("--pull=never") + 1] == "--network=none"
    assert run[run.index("--entrypoint") + 2] == "sha256:abc"
    assert calls[3] == ["docker", "rm", "-f", run[run.index("--name") + 1]]


def test_smoke_rejects_busy_gpu_before_container_and_reports_failed_cuda() -> None:
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, '{"nvidia":{}}', "")
        if argv[1] == "image":
            return subprocess.CompletedProcess(argv, 0, "sha256:abc", "")
        if argv[1] == "run":
            return subprocess.CompletedProcess(argv, 1, "", "CUDA unavailable")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(ValueError, match="active or unknown"):
        gpu_smoke(
            snapshot(processes=1),
            device_id="GPU-one",
            image="local:cuda",
            locate=lambda _: "/bin/tool",
            command=command,
        )
    assert len(calls) == 1
    result = gpu_smoke(
        snapshot(),
        device_id="GPU-one",
        image="local:cuda",
        locate=lambda _: "/bin/tool",
        command=command,
    )
    assert result["smoke"] == "failed"
    assert "CUDA unavailable" in result["issues"][0]
    assert calls[-1][1:3] == ["rm", "-f"]
