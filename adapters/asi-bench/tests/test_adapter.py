import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from agent_infra_asi_bench import Adapter
from agent_infra_asi_bench.backend import AsiBenchBackend
from agent_infra_asi_bench.bundle import build_local_bundle
from agent_infra_asi_bench.codex import CodexAdapter

from agent_infra.benchmarks.api import CandidateRef, Parameter, PlanRequest
from agent_infra.environments.api import ProcessCommand
from agent_infra.environments.execution_api import ExecutionSpec

ASI_ROOT = Path(os.environ.get("ASI_BENCH_CHECKOUT", "/missing/ASI-Bench"))
INSTANCE = ASI_ROOT / "bench_runs/instances_seed31415/math.sigma_linear_diophantine__seed31415"
pytestmark = pytest.mark.skipif(
    not INSTANCE.is_dir(), reason="set ASI_BENCH_CHECKOUT to the pinned upstream checkout"
)


def request(*, prompt: str = "b1", agent: str = "fixture") -> PlanRequest:
    return PlanRequest(
        selection=(INSTANCE.name,),
        candidate=CandidateRef(
            candidate_id="engineering",
            agent=agent,
            agent_version="1.0.0",
            model="none",
            configuration_digest="sha256:" + "0" * 64,
        ),
        parameters=(
            Parameter(key="prompt_level", value=prompt),
            Parameter(key="tasks_dir", value=str(ASI_ROOT / "tasks")),
            Parameter(key="timeout_seconds", value="300"),
        ),
    )


def test_plan_preserves_native_identity_and_score_boundary():
    adapter = Adapter()
    catalog = adapter.discover(INSTANCE)
    plan = adapter.plan(catalog, request())
    assert adapter.validate(plan) == ()
    assert plan.units[0].native_id == INSTANCE.name
    assert plan.request.parameters[0].value == "b1"
    assert plan.phases[0].resources.gpu_count == 0
    assert "non-official" in plan.limitations[1]


def test_unsupported_agent_is_rejected():
    adapter = Adapter()
    plan = adapter.plan(adapter.discover(INSTANCE), request(agent="codex_cli"))
    assert adapter.validate(plan)[0].code == "unsupported_native_profile"


def test_native_codex_profile_preserves_upstream_sandbox_and_resource_envelope():
    adapter = CodexAdapter()
    request = PlanRequest(
        selection=(INSTANCE.name,),
        candidate=CandidateRef(
            candidate_id="codex-test",
            agent="codex_cli",
            agent_version="asibench-0.1.5",
            model="gpt-5.6-sol",
            configuration_digest="sha256:" + "0" * 64,
        ),
        parameters=(
            Parameter(key="prompt_level", value="b1"),
            Parameter(key="tasks_dir", value=str(ASI_ROOT / "tasks")),
            Parameter(key="timeout_seconds", value="300"),
        ),
    )
    plan = adapter.plan(adapter.discover(INSTANCE), request)
    assert adapter.validate(plan) == ()
    assert plan.suite.profile == "seed31415-single-codex-os-v1"
    assert plan.phases[0].resources.cpu_cores == 4
    assert plan.phases[0].resources.memory_bytes == 8 * 1024**3
    invocation = adapter.invocation(plan)
    assert invocation.outputs[-2:] == ("evidence", "docker-observations.jsonl")
    assert '"mode":"codex_os"' in invocation.command.argv[-1]
    assert '"model":"gpt-5.6-sol"' in invocation.command.argv[-1]


def test_codex_profile_rejects_wrong_agent_and_loopback_proxy_without_host_network():
    adapter = CodexAdapter()
    plan = adapter.plan(adapter.discover(INSTANCE), request(agent="fixture"))
    assert adapter.validate(plan)[0].code == "unsupported_native_profile"
    valid = PlanRequest(
        selection=(INSTANCE.name,),
        candidate=CandidateRef(
            candidate_id="codex-test",
            agent="codex_cli",
            agent_version="asibench-0.1.5",
            model="gpt-5.6-sol",
            configuration_digest="sha256:" + "0" * 64,
        ),
        parameters=(
            Parameter(key="tasks_dir", value=str(ASI_ROOT / "tasks")),
            Parameter(key="proxy_url", value="http://127.0.0.1:17890"),
        ),
    )
    plan = adapter.plan(adapter.discover(INSTANCE), valid)
    assert adapter.validate(plan)[0].code == "unsupported_native_profile"


def test_interpret_never_promotes_local_score(tmp_path: Path):
    result = tmp_path / "outputs"
    result.mkdir()
    (result / "native-result.json").write_text(
        json.dumps(
            {
                "local_score": 1.25,
                "local_score_official": False,
                "official_score": None,
                "evaluation_status": "completed",
                "attempt_status": "completed",
                "task_id": "math.sigma_linear_diophantine",
                "instance_id": INSTANCE.name,
                "prompt_level": "b1",
            }
        )
    )
    interpreted = Adapter().interpret(tmp_path)
    assert interpreted["evaluation"] == "scored"
    assert interpreted["metrics"] == {"local_public_score": 1.25}
    assert interpreted["official_score"] is None
    assert interpreted["submission"] == "not_requested"


@pytest.mark.parametrize("official", [True, None, "false"])
def test_interpret_rejects_ambiguous_official_flag(tmp_path: Path, official):
    result = tmp_path / "outputs"
    result.mkdir()
    (result / "native-result.json").write_text(
        json.dumps(
            {
                "local_score": 1.0,
                "local_score_official": official,
                "official_score": None,
                "evaluation_status": "completed",
            }
        )
    )
    assert Adapter().interpret(tmp_path)["protocol"] == "invalid"


def test_seed42_bundle_is_local_and_has_no_official_score(tmp_path: Path):
    results = tmp_path / "results"
    task = results / "math.task"
    task.mkdir(parents=True)
    (task / "attempt.json").write_text(
        json.dumps(
            {
                "task_id": "math.task",
                "instance_id": "math.task__seed42",
                "prompt_level": "b1",
                "agent_name": "fixture",
                "status": "completed",
                "provenance": {
                    "sandbox": {
                        "effective_mode": "os",
                        "enforcement_status": "fail_closed",
                        "verification_status": "docker_container",
                        "image_identity": "sha256:" + "1" * 64,
                    }
                },
                "agent_output": {"persisted_outputs": {"files": []}},
            }
        )
    )
    outcome = build_local_bundle(results, tmp_path / "bundle")
    assert outcome["uploaded"] is False
    assert outcome["authenticated"] is False
    assert outcome["official_score"] is None
    assert (tmp_path / "bundle" / "manifest.json").is_file()


def test_seed31415_cannot_be_bundled_as_official(tmp_path: Path):
    task = tmp_path / "results" / "math.task"
    task.mkdir(parents=True)
    (task / "attempt.json").write_text(
        json.dumps(
            {
                "task_id": "math.task",
                "instance_id": "math.task__seed31415",
                "provenance": {"sandbox": {}},
            }
        )
    )
    with pytest.raises(ValueError, match="only accepts seed42"):
        build_local_bundle(tmp_path / "results", tmp_path / "bundle")


def test_backend_cancel_does_not_signal_unrelated_process(tmp_path: Path):
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    backend = AsiBenchBackend(tmp_path / "backend")
    spec = ExecutionSpec(
        run_id="run",
        attempt_id="attempt",
        unit_id="unit",
        phase_id="native",
        workspace=str(tmp_path / "work"),
        command=ProcessCommand(
            (sys.executable, "-c", "import time; time.sleep(5)"),
            cwd=".",
            timeout_seconds=5,
        ),
    )
    try:
        handle = backend.submit("owned", spec)
        backend.cancel(handle)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not backend.cleanup(handle).complete:
            time.sleep(0.025)
        assert backend.cleanup(handle).complete
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=2)
