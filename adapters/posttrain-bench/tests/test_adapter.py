import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from agent_infra_posttrain_bench import Adapter
from agent_infra_posttrain_bench.backend import PostTrainBackend
from agent_infra_posttrain_bench.handoff import freeze_model
from agent_infra_posttrain_bench.request import AGENT_VERSION, REVISION, Request
from agent_infra_posttrain_bench.runner import run as run_engineering
from agent_infra_posttrain_bench.source import runner_digest, scheduler_digest

from agent_infra.benchmarks.api import CandidateRef, Parameter, PinnedSource, PlanRequest
from agent_infra.environments.api import ProcessCommand
from agent_infra.environments.execution_api import ExecutionSpec

UPSTREAM = Path(os.environ.get("POSTTRAIN_BENCH_CHECKOUT", "/missing/PostTrainBench"))
pytestmark = pytest.mark.skipif(
    not (UPSTREAM / ".git").is_dir(),
    reason="set POSTTRAIN_BENCH_CHECKOUT to the pinned upstream checkout",
)


def engineering_request() -> PlanRequest:
    return PlanRequest(
        selection=("gsm8k",),
        candidate=CandidateRef(
            candidate_id="engineering",
            agent="protocol-fixture",
            agent_version="1.0.0",
            model="none",
            configuration_digest="sha256:" + "0" * 64,
        ),
        parameters=(
            Parameter(key="mode", value="engineering"),
            Parameter(key="model_to_train", value="Qwen/Qwen3-1.7B-Base"),
            Parameter(key="num_hours", value="1"),
            Parameter(key="num_gpus", value="0"),
            Parameter(key="timeout_seconds", value="120"),
        ),
    )


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("posttrain-source") / "checkout"
    subprocess.run(["git", "clone", "--shared", str(UPSTREAM), str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", REVISION], check=True)
    return target


def test_plan_preserves_task_budget_visibility_and_no_platform_retry(checkout: Path):
    adapter = Adapter()
    task = checkout / "src/eval/tasks/gsm8k"
    catalog = adapter.discover(task)
    plan = adapter.plan(catalog, engineering_request())
    assert adapter.validate(plan) == ()
    assert plan.units[0].kind == "native_job"
    phase = plan.phases[0]
    assert phase.resources.gpu_count == 0 and phase.resources.allocator == "local"
    assert {item.material_id for item in phase.materials} == {
        "native-evaluation-task",
        "native-runner-and-judges",
    }
    assert plan.retry.owner == "none" and plan.retry.max_attempts == 1


def test_protocol_digest_ignores_untracked_runtime_files(checkout: Path):
    before = runner_digest(checkout)
    cache = checkout / "src/eval/general/__pycache__/runtime-cache.pyc"
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(b"not part of the pinned protocol")
    assert runner_digest(checkout) == before


def test_native_plan_requires_pinned_target_and_scheduler_paths(checkout: Path):
    adapter = Adapter()
    catalog = adapter.discover(checkout / "src/eval/tasks/gsm8k")
    request = engineering_request().model_copy(
        update={
            "candidate": CandidateRef(
                candidate_id="native",
                agent="codex",
                agent_version=AGENT_VERSION,
                model="gpt-5.6-sol",
                configuration_digest="sha256:" + "1" * 64,
            ),
            "parameters": (
                Parameter(key="mode", value="native"),
                Parameter(key="model_to_train", value="Qwen/Qwen3-1.7B-Base"),
                Parameter(key="num_gpus", value="1"),
            ),
        }
    )
    issue = adapter.validate(adapter.plan(catalog, request))[0]
    assert "target_model" in issue.message
    pinned = request.candidate.model_copy(
        update={
            "target_model": PinnedSource(
                uri="hf://Qwen/Qwen3-1.7B-Base",
                revision="0123456789abcdef",
                digest="sha256:" + "2" * 64,
            )
        }
    )
    issue = adapter.validate(
        adapter.plan(catalog, request.model_copy(update={"candidate": pinned}))
    )[0]
    assert "absolute results_root" in issue.message


def test_engineering_runner_freezes_model_and_interprets_non_official(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    adapter = Adapter()
    plan = adapter.plan(adapter.discover(checkout / "src/eval/tasks/gsm8k"), engineering_request())
    invocation = adapter.invocation(plan)
    monkeypatch.chdir(tmp_path)
    assert run_engineering(Request.model_validate_json(invocation.command.argv[-1])) == 0
    handoff = json.loads((tmp_path / "model-handoff.json").read_text())
    assert handoff["immutable"] is True and handoff["file_count"] == 2
    collected = tmp_path / "collected/outputs"
    collected.mkdir(parents=True)
    for name in invocation.outputs:
        source = tmp_path / name
        shutil.copytree(source, collected / name) if source.is_dir() else shutil.copyfile(
            source, collected / name
        )
    result = adapter.interpret(tmp_path / "collected")
    assert result["protocol"] == "valid" and result["engineering_fixture"] is True
    assert result["score_eligible"] is False and result["official"] is False


def test_model_handoff_rejects_symlinks(tmp_path: Path):
    source = tmp_path / "model"
    source.mkdir()
    (source / "config.json").write_text("{}")
    (source / "outside").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        freeze_model(source, tmp_path / "store", 1024)


def test_model_handoff_is_content_addressed_and_idempotent(tmp_path: Path):
    source = tmp_path / "model"
    source.mkdir()
    (source / "config.json").write_text("{}")
    (source / "weights").write_bytes(b"stable")
    first = freeze_model(source, tmp_path / "store", 1024)
    second = freeze_model(source, tmp_path / "store", 1024)
    assert first == second
    assert Path(first["uri"].removeprefix("file://")).is_dir()


def _script(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o700)


def _native_result(path: Path) -> None:
    model = path / "final_model"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    (model / "model.safetensors").write_bytes(b"weights")
    (path / "metrics.json").write_text('{"accuracy": 0.42}')
    (path / "time_taken.txt").write_text("00:10:00\n")
    (path / "judgement_gpt5_4.json").write_text(
        '{"contamination": false, "disallowed_model": false}'
    )
    (path / "judgement_api.json").write_text('{"disallowed_api_usage": false}')
    (path / "judgement_ptb_lookup.json").write_text('{"disallowed_ptb_lookup": false}')


def test_condor_backend_owns_native_id_cleanup_and_external_handoff(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    results = tmp_path / "results"
    store = tmp_path / "models"
    bins = tmp_path / "bin"
    state = tmp_path / "scheduler-state.json"
    results.mkdir()
    store.mkdir(mode=0o700)
    bins.mkdir()
    config = checkout / ".env"
    config.write_text(f'POST_TRAIN_BENCH_RESULTS_DIR="{results}"\n')
    config.chmod(0o600)
    _script(
        bins / "condor_submit",
        "import json\nfrom pathlib import Path\n"
        f"p=Path({str(state)!r})\n"
        "p.write_text(json.dumps({'where':'q','status':2}))\n"
        "print('731.0')\n",
    )
    query = (
        f"import json\nfrom pathlib import Path\np=Path({str(state)!r}); "
        "s=json.loads(p.read_text()) if p.exists() else {'where':'none','status':0}; "
        "print(json.dumps([{'ClusterId':731,'ProcId':0,'JobStatus':s['status'],"
        "'ExitCode':0}] if s['where']==WHERE else []))\n"
    )
    _script(bins / "condor_q", "WHERE='q'\n" + query)
    _script(bins / "condor_history", "WHERE='history'\n" + query)
    _script(
        bins / "condor_rm",
        "import json\nfrom pathlib import Path\n"
        f"p=Path({str(state)!r})\n"
        "p.write_text(json.dumps({'where':'history','status':3}))\n",
    )
    request = Request(
        mode="native",
        checkout_root=str(checkout),
        task="gsm8k",
        task_digest="sha256:" + "1" * 64,
        runner_digest="sha256:" + "2" * 64,
        agent="codex",
        agent_config="gpt-5.6-sol",
        model_to_train="Qwen/Qwen3-1.7B-Base",
        num_hours=10,
        num_gpus=1,
        request_cpus=16,
        request_memory_mb=131072,
        request_disk_gb=400,
        timeout_seconds=79200,
        results_root=str(results),
        model_store=str(store),
        scheduler_bin_dir=str(bins),
        scheduler_digest=scheduler_digest(bins),
        max_model_bytes=1024,
    )
    workspace = tmp_path / "workspace"
    spec = ExecutionSpec(
        run_id="run",
        attempt_id="attempt",
        unit_id="gsm8k",
        phase_id="native-training-trial",
        command=ProcessCommand(
            (sys.executable, "-m", "agent_infra_posttrain_bench.runner", request.model_dump_json()),
            cwd=".",
            timeout_seconds=request.timeout_seconds,
        ),
        workspace=str(workspace),
        outputs=("native-result.json", "model-handoff.json", "evidence"),
        max_log_bytes=1024**2,
        max_artifact_bytes=4 * 1024**2,
    )
    backend = PostTrainBackend(tmp_path / "backend")
    handle = backend.submit("native-operation", spec)
    assert handle.native_id == "condor:731.0"
    recovered = PostTrainBackend(tmp_path / "backend").reconcile("native-operation")
    assert recovered.state == "known" and recovered.handle == handle
    assert backend.observe(handle).status == "running"
    root = backend._path("native-operation")
    tag = json.loads((root / "intent.json").read_text())["tag"]
    native_result = backend._result_path(request, "731.0", tag)
    _native_result(native_result)
    state.write_text('{"where":"history","status":4}')
    assert backend.observe(handle).status == "completed"
    assert backend.cleanup(handle).complete is True
    submission = backend.collect(handle)
    document = json.loads((submission.root / "outputs/native-result.json").read_text())
    assert document["protocol"] == "native_valid" and document["score_eligible"] is True
    assert Path(
        json.loads((submission.root / "outputs/model-handoff.json").read_text())["uri"][7:]
    ).is_dir()

    cancelled = backend.submit("cancel-operation", spec.model_copy(update={"run_id": "cancel"}))
    assert backend.cancel(cancelled).complete is True
    assert backend.observe(cancelled).status == "cancelled"

    # A lost submit reply cannot prove that HTCondor did not launch the job.
    # Leave the durable intent in place and refuse a second automatic submit.
    calls = 0
    monkeypatch.setattr(backend, "_receipt", lambda *_: None)

    def ambiguous_submit(*_args: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(backend, "_run", ambiguous_submit)
    ambiguous = spec.model_copy(update={"run_id": "ambiguous"})
    with pytest.raises(RuntimeError, match="did not return a native job ID"):
        backend.submit("ambiguous-operation", ambiguous)
    with pytest.raises(RuntimeError, match="native submit outcome is unknown"):
        backend.submit("ambiguous-operation", ambiguous)
    assert calls == 1
