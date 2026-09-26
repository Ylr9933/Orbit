"""Native configuration and archival boundaries; no model or Docker calls."""

import json
from types import SimpleNamespace

import pytest
from agent_infra_harbor import agent
from agent_infra_harbor.evidence import inventory
from agent_infra_harbor.request import Request


def request(**kwargs):
    return Request(
        task="/task",
        task_digest="sha256:" + "0" * 64,
        agent="codex",
        model="gpt-6-sol",
        codex_version="0.157.1",
        **kwargs,
    )


def test_owned_auth_path_only_and_no_ambient_config(tmp_path, monkeypatch):
    auth = tmp_path / ".codex/auth.json"
    auth.parent.mkdir()
    auth.write_text('{"secret": "do-not-export"}')
    monkeypatch.setattr(agent.pwd, "getpwuid", lambda _: SimpleNamespace(pw_dir=str(tmp_path)))
    monkeypatch.setenv("CODEX_FORCE_AUTH_JSON", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-export")
    config = agent.configuration(request())
    assert config["env"] == {"CODEX_AUTH_JSON_PATH": str(auth)}
    assert "do-not-export" not in json.dumps(config)
    assert config["kwargs"]["version"] == "0.157.1"
    auth.unlink()
    auth.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="owned"):
        agent.configuration(request())


def test_api_key_is_not_serialized(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    key = tmp_path / "key"
    key.write_text("private-api-token")
    key.chmod(0o600)
    configured = request(auth_mode="api_key", api_key_file=str(key))
    config = agent.configuration(configured)
    assert "private-api-token" not in json.dumps(config)
    assert "private-api-token" not in configured.model_dump_json()
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        agent.configuration(configured)


def test_native_inventory_keeps_raw_and_marks_clipped_view(tmp_path):
    root = tmp_path / "trials/one"
    (root / "agent/sessions").mkdir(parents=True)
    (root / "verifier").mkdir()
    (root / "artifacts").mkdir()
    (root / "result.json").write_text("{}")
    (root / "verifier/reward.txt").write_text("0.5")
    (root / "artifacts/output.txt").write_text("result")
    (root / "agent/sessions/rollout.jsonl").write_text('{"type":"session_meta"}\n')
    trajectory = {"session_id": "session", "steps": [{"source": "agent", "message": "x" * 5000}]}
    (root / "agent/trajectory.json").write_text(json.dumps(trajectory))
    evidence = inventory(tmp_path, "codex")
    assert evidence["capture_status"] == "complete"
    assert evidence["trajectory"]["capture_status"] == "truncated"
    assert evidence["trajectory"]["session_id"] == "session"
    assert (root / "agent/trajectory.json").read_text() == json.dumps(trajectory)
    assert evidence["groups"]["submission"]
    (root / "agent/sessions/rollout.jsonl").unlink()
    assert "native_sessions" in inventory(tmp_path, "codex")["missing"]


def test_native_inventory_rejects_credentials(tmp_path):
    logs = tmp_path / "trials/one/agent"
    logs.mkdir(parents=True)
    (logs / "auth.json").write_text("{}")
    with pytest.raises(ValueError, match="credential"):
        inventory(tmp_path, "codex")


def test_failure_before_trial_still_writes_cleanup_and_inventory(tmp_path, monkeypatch):
    import asyncio

    from agent_infra_harbor import runner

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "content_digest", lambda _: "wrong")
    monkeypatch.setattr(runner.environment, "ENVIRONMENTS", [])
    with pytest.raises(ValueError, match="snapshot"):
        asyncio.run(runner.run(request()))
    assert json.loads((tmp_path / "native-cleanup.json").read_text())["complete"]
    assert (
        json.loads((tmp_path / "native-evidence.json").read_text())["capture_status"]
        == "incomplete"
    )


def test_collection_blocks_credential_files_before_records(tmp_path, monkeypatch):
    from agent_infra_harbor.backend import HarborBackend

    backend = HarborBackend(tmp_path / "backend")
    (tmp_path / "native-evidence.json").write_text("{}")
    logs = tmp_path / "trials/agent"
    logs.mkdir(parents=True)
    (logs / "auth.json").write_text("{}")
    monkeypatch.setattr(
        backend,
        "spec",
        lambda _: SimpleNamespace(workspace=str(tmp_path), outputs=("native-evidence.json",)),
    )
    with pytest.raises(ValueError, match="credential"):
        backend.collect(None)


def test_bundle_freezes_contents_and_checks_container_version(tmp_path):
    import asyncio

    from agent_infra_harbor.bundle import install, validate_bundle

    from agent_infra.contracts.files import content_digest

    bundle = tmp_path / "bundle"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "bin/codex").write_text("native test binary")
    (bundle / "codex-path").mkdir()
    (bundle / "codex-path/rg").write_text("native search binary")
    digest = content_digest(bundle)
    assert validate_bundle(str(bundle), digest) == bundle

    class Environment:
        async def upload_dir(self, source, target):
            assert source == bundle and target == "/opt/agent-infra-codex"

        async def exec(self, **kwargs):
            return SimpleNamespace(stdout="codex-cli 0.157.1\n", return_code=0)

    evidence = tmp_path / "codex.json"
    asyncio.run(install(Environment(), str(bundle), digest, "0.157.1", evidence))
    assert json.loads(evidence.read_text())["version"] == "0.157.1"
    with pytest.raises(RuntimeError, match="incompatible"):
        asyncio.run(install(Environment(), str(bundle), digest, "0.1.0", evidence))
    (bundle / "bin/codex").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        validate_bundle(str(bundle), digest)
