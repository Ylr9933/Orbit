"""Real Linux processes only: temporary workspaces, <=5 seconds/job, no external services."""

import hashlib
import json
import os
import signal
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from agent_infra.environments.api import ProcessCommand
from agent_infra.environments.execution_api import ExecutionSpec
from agent_infra.environments.managed_process import ManagedProcessBackend

pytestmark = pytest.mark.integration


def spec(root, code, *, timeout=3, outputs=(), log_limit=8 * 1024**2):
    return ExecutionSpec(
        run_id="run",
        attempt_id="attempt",
        unit_id="unit",
        phase_id="native",
        workspace=str(root / "work"),
        command=ProcessCommand((sys.executable, "-c", code), cwd=".", timeout_seconds=timeout),
        outputs=outputs,
        max_log_bytes=log_limit,
    )


def wait(backend, handle):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        observation = backend.observe(handle)
        if observation.eof and observation.cleanup.complete:
            return observation
        time.sleep(0.025)
    backend.cancel(handle)
    raise AssertionError("owned process did not produce a clean terminal receipt")


def test_reinstantiation_and_duplicate_submission_do_not_restart(tmp_path):
    root = tmp_path
    backend = ManagedProcessBackend(root / "native")
    request = spec(
        root,
        "from pathlib import Path; import time; "
        "p=Path('count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
        "print('hello',flush=True); time.sleep(.2)",
        outputs=("count",),
    )
    handle = backend.submit("operation", request)
    recovered = ManagedProcessBackend(root / "native")
    duplicate = recovered.submit("operation", request)
    assert handle.spec_digest == duplicate.spec_digest
    done = wait(recovered, duplicate)
    assert done.status == "completed" and done.data == b"hello\n"
    frozen = recovered.collect(duplicate)
    assert (frozen.root / "outputs/count").read_text() == "1"
    assert recovered.collect(duplicate) == frozen
    conflict = request.model_copy(update={"command": replace(request.command, argv=("false",))})
    with pytest.raises(ValueError, match="different execution spec"):
        recovered.submit("operation", conflict)


@pytest.mark.parametrize("action", ["timeout", "cancel"])
def test_timeout_and_cancel_kill_background_group_members(tmp_path, action):
    backend = ManagedProcessBackend(tmp_path / "native")
    code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)']); "
        "Path('child').write_text(str(child.pid)); print('running',flush=True); time.sleep(5)"
    )
    handle = backend.submit("job", spec(tmp_path, code, timeout=0.7 if action == "timeout" else 3))
    child_file = tmp_path / "work/child"
    for _ in range(100):
        if child_file.exists():
            break
        time.sleep(0.02)
    assert child_file.exists()
    if action == "cancel":
        backend.cancel(handle)
    done = wait(backend, handle)
    assert done.status == ("timed_out" if action == "timeout" else "cancelled")
    child_stat = Path(f"/proc/{child_file.read_text()}/stat")
    assert not child_stat.exists() or child_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"


def test_main_exit_also_cleans_background_children_and_bounded_logs(tmp_path):
    backend = ManagedProcessBackend(tmp_path / "native")
    handle = backend.submit(
        "job",
        spec(
            tmp_path,
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)']); "
            "sys.stdout.buffer.write(b'x'*10000)",
            log_limit=64,
        ),
    )
    done = wait(backend, handle)
    assert done.status == "completed" and done.logs_truncated and len(done.data) == 64
    with pytest.raises(ValueError, match="cursor"):
        backend.observe(handle, 65)


def test_launch_intent_without_acknowledgement_is_not_replayed(tmp_path, monkeypatch):
    backend = ManagedProcessBackend(tmp_path / "native")
    calls = []

    def lost(*args, **kwargs):
        calls.append(args)
        raise OSError("simulated crash between launch intent and Popen")

    monkeypatch.setattr("agent_infra.environments.managed_process.subprocess.Popen", lost)
    request = spec(tmp_path, "print('never runs')")
    with pytest.raises(OSError):
        backend.submit("job", request)
    recovered = ManagedProcessBackend(tmp_path / "native")
    handle = recovered.submit("job", request)
    assert len(calls) == 1 and recovered.reconcile("job").state == "unknown"
    assert not recovered.cleanup(handle).complete


def test_dead_supervisor_keeps_unknown_instead_of_assuming_cleanup(tmp_path):
    backend = ManagedProcessBackend(tmp_path / "native")
    handle = backend.submit("job", spec(tmp_path, "import time; time.sleep(.5)"))
    root = tmp_path / "native" / hashlib.sha256(b"job").hexdigest()
    for _ in range(100):
        if (root / "owner.json").exists():
            break
        time.sleep(0.02)
    owner = json.loads((root / "owner.json").read_text())
    # Only this test's exact supervisor; its bounded child naturally exits within .5s.
    descriptor = os.pidfd_open(owner["pid"])
    try:
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
    finally:
        os.close(descriptor)
    time.sleep(0.6)
    assert backend.reconcile("job").state == "unknown"
    assert not backend.cleanup(handle).complete
    assert (
        backend.submit("job", spec(tmp_path, "import time; time.sleep(.5)")).spec_digest
        == handle.spec_digest
    )


def test_collection_rejects_symlinks_and_marks_missing_outputs(tmp_path):
    backend = ManagedProcessBackend(tmp_path / "native")
    handle = backend.submit(
        "job",
        spec(
            tmp_path,
            "from pathlib import Path; Path('bad').symlink_to('/etc/hostname')",
            outputs=("bad", "missing"),
        ),
    )
    wait(backend, handle)
    with pytest.raises(ValueError, match="symlink"):
        backend.collect(handle)
    (tmp_path / "work/bad").unlink()
    result = backend.collect(handle)
    assert result.missing == ("bad", "missing")


def test_child_does_not_inherit_host_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("BM01_TEST_SECRET", "not-a-real-secret")
    backend = ManagedProcessBackend(tmp_path / "native")
    handle = backend.submit(
        "job",
        spec(tmp_path, "import os; print(os.environ.get('BM01_TEST_SECRET','absent'),flush=True)"),
    )
    assert wait(backend, handle).data == b"absent\n"
