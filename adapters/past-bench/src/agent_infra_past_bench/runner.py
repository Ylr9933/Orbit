"""Run and verify one pinned PAST-Bench paired family."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import past_bench
from past_bench.cli import main as past_main
from past_bench.models.self_evolve import SelfEvolveSequenceDefinition
from past_bench.self_evolve_v2 import generate_manifest

from agent_infra.contracts.files import content_digest

from .engineering import run as run_engineering
from .request import JUDGE_KEY_ENVS, PAST_REVISION, PAST_VERSION, Request


def _revision(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _runner_digest() -> str:
    if importlib.metadata.version("past-bench") != PAST_VERSION:
        raise ValueError("installed PAST-Bench version changed")
    package = Path(past_bench.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _secret(path_value: str) -> str:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("credential reference must be an absolute regular file")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("credential file must not be accessible by group or others")
    if path.stat().st_size > 65536:
        raise ValueError("credential file is unexpectedly large")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError("credential file is empty")
    return value


def _primary(
    sequence: SelfEvolveSequenceDefinition, document: dict[str, Any]
) -> list[dict[str, Any]]:
    labels = {episode.label for episode in sequence.episodes}
    return [item for item in document.get("episodes", []) if item.get("label") in labels]


def _verify_outputs(
    sequence: SelfEvolveSequenceDefinition, output: Path
) -> tuple[bool, dict[str, Any]]:
    expected = [episode.label for episode in sequence.episodes]
    result_documents = {}
    state_roots = {}
    valid = True
    for variant in ("with_persistence", "without_persistence"):
        path = output / variant / "sequence_results.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        primary = _primary(sequence, document)
        observed = [item.get("label") for item in primary]
        same_length = len(primary) == len(sequence.episodes)
        valid &= same_length and observed == expected
        if same_length:
            valid &= all(
                item.get("requires_fresh_session") == episode.requires_fresh_session
                for item, episode in zip(primary, sequence.episodes, strict=True)
            )
            valid &= all(
                item.get("history_mode") == episode.history_mode
                for item, episode in zip(primary, sequence.episodes, strict=True)
            )
        result_documents[variant] = {
            "episodes": observed,
            "count": len(primary),
            "infra_blocked": [item.get("label") for item in primary if item.get("infra_blocked")],
        }
        roots = {
            item.get("runtime_family_home") for item in primary if item.get("runtime_family_home")
        }
        state_roots[variant] = sorted(roots)
    comparison = json.loads((output / "sequence_comparison.json").read_text(encoding="utf-8"))
    valid &= set(comparison) >= {"with_persistence", "without_persistence", "delta"}
    engineering_evidence = output / "state_evidence.json"
    if engineering_evidence.is_file():
        items = json.loads(engineering_evidence.read_text(encoding="utf-8"))["items"]
        sessions = [item["session_id"] for item in items]
        scopes = {
            variant: {item["state_scope"] for item in items if item["variant"] == variant}
            for variant in ("with_persistence", "without_persistence")
        }
        valid &= len(sessions) == len(set(sessions)) == 2 * len(expected)
        valid &= scopes["with_persistence"].isdisjoint(scopes["without_persistence"])
        valid &= not any(
            item["state_visible"] for item in items if item["variant"] == "without_persistence"
        )
        state_roots = {key: sorted(value) for key, value in scopes.items()}
    if all(state_roots.values()):
        valid &= set(state_roots["with_persistence"]).isdisjoint(state_roots["without_persistence"])
    return valid, {
        "episode_order": expected,
        "variants": result_documents,
        "state_roots": state_roots,
        "paired_delta": comparison.get("delta", {}),
    }


def run(request: Request) -> int:
    root = Path.cwd()
    checkout = Path(request.checkout_root).resolve()
    family = Path(request.family_dir).resolve()
    if _revision(checkout) != PAST_REVISION:
        raise ValueError("PAST-Bench checkout revision changed")
    if _runner_digest() != request.runner_digest:
        raise ValueError("installed PAST-Bench runner changed after planning")
    if content_digest(family) != request.family_digest:
        raise ValueError("PAST-Bench family changed after planning")
    if content_digest(checkout / "config.yaml") != request.config_digest:
        raise ValueError("PAST-Bench config changed after planning")
    if content_digest(checkout / "configs" / "agents.yaml") != request.registry_digest:
        raise ValueError("PAST-Bench agent registry changed after planning")

    manifest = root / "native-manifest.yaml"
    generate_manifest(request.family_rel, out_path=manifest, repo_root=checkout)
    sequence = SelfEvolveSequenceDefinition.from_yaml(manifest)
    output = root / "past-output"
    if request.mode == "engineering":
        run_engineering(manifest, output)
    else:
        agent_key = _secret(request.agent_key_file)
        argv = [
            "evolve",
            "--sequence",
            str(manifest),
            "--agent",
            request.agent,
            "--model",
            request.model,
            "--api-key",
            agent_key,
            "--config",
            str(checkout / "config.yaml"),
            "--registry",
            str(checkout / "configs" / "agents.yaml"),
            "--runtime",
            "local",
            "--trace-dir",
            str(output),
            "--compare-no-persistence",
        ]
        if request.agent_profile:
            argv.extend(("--agent-profile", request.agent_profile))
        if request.sandbox_tools:
            argv.append("--sandbox-tools")
        if request.judge_key_file:
            if request.judge_key_env not in JUDGE_KEY_ENVS:
                raise ValueError("unsupported judge credential environment")
            os.environ[request.judge_key_env] = _secret(request.judge_key_file)
            if request.judge_model:
                argv.extend(("--judge-model", request.judge_model))
        else:
            argv.append("--no-judge")
        past_main(argv)

    valid, evidence = _verify_outputs(sequence, output)
    result = {
        "benchmark": "PAST-Bench",
        "upstream_revision": PAST_REVISION,
        "family": request.family_rel,
        "mode": request.mode,
        "agent": request.agent,
        "model": request.model,
        "conditions": ["with_persistence", "without_persistence"],
        "pair_complete": valid,
        "protocol": "engineering_valid"
        if valid and request.mode == "engineering"
        else "valid"
        if valid and request.judge_key_file
        else "review_required",
        "official": False,
        "submission": "not_requested",
        "evidence": evidence,
    }
    (root / "native-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(run(Request.model_validate_json(sys.argv[1])))
