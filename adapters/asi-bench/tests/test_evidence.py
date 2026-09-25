"""Native sidecar coverage and path constraints without model or Docker calls."""

import json
import os
import subprocess
import sys

from agent_infra_asi_bench.docker_proxy import summarize
from agent_infra_asi_bench.evidence import capture
from agent_infra_asi_bench.request import Request
from agent_infra_asi_bench.runner import _write_failure


def test_captures_declared_native_trace_and_session(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    result = native / "task__seed31415__b1.json"
    stdout = native / "task__seed31415__b1.agent_stdout.jsonl"
    stdout.write_text(
        json.dumps({"type": "thread.started", "thread_id": "thread-1"})
        + "\n"
        + json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}})
        + "\n"
    )
    trace = native / "task__seed31415__b1.trajectory.json"
    trace.write_text(
        json.dumps(
            [
                {
                    "step_index": 0,
                    "step_type": "tool_call",
                    "content": "shell",
                    "metadata": {"tool_name": "shell", "secret": "not-for-view"},
                },
            ]
        )
    )
    index = capture(
        result,
        {
            "instance_id": "task__seed31415",
            "agent_output": {"raw_stdout_file": stdout.name, "trajectory_file": trace.name},
        },
        tmp_path / "evidence",
        docker={"container_id": "abc"},
    )
    assert index["capture_status"] == "complete"
    assert index["trajectory"]["session_id"] == "thread-1"
    assert index["calls"]["completed_turns"] == 0
    assert json.loads((tmp_path / "evidence" / "trajectory-view.json").read_text())[0][
        "metadata"
    ] == {"tool_name": "shell"}
    assert (tmp_path / "evidence" / "codex-stdout.jsonl").read_bytes() == stdout.read_bytes()


def test_rejects_parent_reference_and_marks_missing_trace(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    index = capture(
        native / "result.json",
        {"agent_output": {"raw_stdout_file": "../secret", "trajectory_file": "missing.json"}},
        tmp_path / "evidence",
        docker={},
    )
    assert index["capture_status"] == "partial"
    assert index["files"]["raw_stdout_file"]["capture_status"] == "invalid_reference"
    assert index["files"]["trajectory_file"]["capture_status"] == "missing"


def test_derives_normalized_steps_from_native_codex_jsonl(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    stdout = native / "agent.jsonl"
    stdout.write_text(
        "\n".join(
            json.dumps(event)
            for event in (
                {"type": "thread.started", "thread_id": "thread-2"},
                {"type": "item.started", "item": {"type": "command_execution", "command": "pwd"}},
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "pwd",
                        "aggregated_output": "/workspace",
                    },
                },
                {"type": "turn.completed", "usage": {"input_tokens": 8, "output_tokens": 4}},
            )
        )
        + "\n"
    )
    index = capture(
        native / "result.json",
        {"instance_id": "task__seed31415", "agent_output": {"raw_stdout_file": stdout.name}},
        tmp_path / "evidence",
        docker={},
    )
    assert index["files"]["trajectory_file"]["capture_status"] == "derived"
    assert index["trajectory"]["session_id"] == "thread-2"
    assert index["calls"]["completed_turns"] == 1
    assert index["calls"]["last_reported_usage"]["output_tokens"] == 4
    assert any(
        step["step_type"] == "tool_call"
        for step in json.loads((tmp_path / "evidence" / "trajectory-view.json").read_text())
    )


def test_summarizes_observed_container_and_usage_without_claiming_full_coverage():
    observations = [
        {
            "kind": "identity",
            "container_id": "owned",
            "cpu_limit": 4_000_000_000,
            "memory_limit_bytes": 8 * 1024**3,
        },
        {"kind": "usage", "sample": {"CPUPerc": "12.5%", "MemUsage": "21MiB / 8GiB"}},
    ]
    result = summarize(observations, "sha256:image")
    assert result["container_id"] == "owned"
    assert result["usage_status"] == "sampled"
    assert result["last_sample"]["CPUPerc"] == "12.5%"
    assert summarize([], "sha256:image")["usage_status"] == "unavailable"


def test_loopback_build_proxy_uses_host_network_only_when_selected(tmp_path):
    output = tmp_path / "args.json"
    fake_docker = tmp_path / "fake-docker"
    fake_docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "open(os.environ['TEST_DOCKER_ARGS'], 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    fake_docker.chmod(0o700)
    environment = {
        **os.environ,
        "AGENT_INFRA_DOCKER_BIN": str(fake_docker),
        "AGENT_INFRA_ASI_BUILD_NETWORK": "host",
        "TEST_DOCKER_ARGS": str(output),
    }
    subprocess.run(
        [sys.executable, "-m", "agent_infra_asi_bench.docker_proxy", "build", "-t", "task", "."],
        env=environment,
        check=True,
    )
    assert json.loads(output.read_text()) == ["build", "--network", "host", "-t", "task", "."]


def test_early_native_failure_preserves_summary_and_evidence(tmp_path):
    request = Request(
        instance_dir="/tmp/instance",
        instance_digest="sha256:1",
        tasks_dir="/tmp/tasks",
        tasks_digest="sha256:2",
        scorer_policy_digest="sha256:3",
        task_id="task",
        instance_id="task__seed31415",
        prompt_level="b1",
        timeout_seconds=60,
        mode="codex_os",
        model="gpt-5.6-sol",
    )
    evidence = {"capture_status": "partial", "trajectory": {}, "calls": {}, "docker": {}}
    assert _write_failure(tmp_path, request, 1, "native prediction absent", evidence) == 1
    summary = json.loads((tmp_path / "native-result.json").read_text())
    assert summary["failure_reason"] == "native prediction absent"
    assert summary["evidence"]["capture_status"] == "partial"
