"""Immutable model snapshots and bounded native evidence views."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from agent_infra.environments.recovery import write_ownership

from .request import REVISION, Request

EVIDENCE_FILES = (
    "metrics.json",
    "time_taken.txt",
    "prompt.txt",
    "solve_out.txt",
    "solve_parsed.txt",
    "cli_version.txt",
    "system_monitor.log",
    "judgement_gpt5_4.json",
    "judgement_gpt5_4_rerun.json",
    "judgement_api.json",
    "judgement_api_rerun.json",
    "judgement_ptb_lookup.json",
    "judgement_ptb_lookup_rerun.json",
    "judgement_general.json",
    "judgement_general_rerun.json",
)
EVIDENCE_LIMIT = 32 * 1024**2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024**2):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _model_files(source: Path, maximum: int) -> tuple[list[dict[str, Any]], int]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("final_model must be a regular directory")
    files: list[dict[str, Any]] = []
    total = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("final_model contains a symlink or special file")
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        if total > maximum:
            raise ValueError("final_model exceeds the authorized handoff budget")
        files.append(
            {
                "path": path.relative_to(source).as_posix(),
                "size_bytes": size,
                "sha256": _sha256(path),
            }
        )
    if not files or not (source / "config.json").is_file():
        raise ValueError("final_model is empty or lacks config.json")
    return files, total


def _tree_digest(files: list[dict[str, Any]]) -> str:
    body = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write_once(path: Path, document: dict[str, Any]) -> None:
    if path.is_file():
        if json.loads(path.read_text(encoding="utf-8")) != document:
            raise ValueError(f"existing {path.name} differs from finalized evidence")
        return
    write_ownership(path, document)


def freeze_model(source: Path, store: Path, maximum: int) -> dict[str, Any]:
    files, total = _model_files(source, maximum)
    digest = _tree_digest(files)
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    if store.is_symlink() or store.stat().st_mode & 0o077:
        raise ValueError("model store must be a private directory")
    destination = store / digest.removeprefix("sha256:")
    manifest = {
        "schema_version": 1,
        "kind": "immutable-model-snapshot",
        "digest": digest,
        "size_bytes": total,
        "files": files,
    }
    if destination.is_symlink():
        raise ValueError("model snapshot destination must not be a symlink")
    if not destination.exists():
        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=store))
        try:
            for item in files:
                source_file = source / item["path"]
                target = temporary / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, target)
                if target.stat().st_size != item["size_bytes"] or _sha256(target) != item["sha256"]:
                    raise ValueError("model changed while creating the immutable snapshot")
            write_ownership(temporary / "MANIFEST.json", manifest)
            for path in temporary.rglob("*"):
                path.chmod(0o440 if path.is_file() else 0o550)
            os.rename(temporary, destination)
        except FileExistsError:
            pass
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    stored = destination / "MANIFEST.json"
    if not stored.is_file() or json.loads(stored.read_bytes()) != manifest:
        raise ValueError("existing model snapshot does not match its content address")
    for path in destination.rglob("*"):
        path.chmod(0o440 if path.is_file() else 0o550)
    destination.chmod(0o550)
    return {
        "schema_version": 1,
        "uri": destination.as_uri(),
        "digest": digest,
        "size_bytes": total,
        "manifest": (destination / "MANIFEST.json").as_uri(),
        "file_count": len(files),
        "immutable": True,
    }


def _judgement(result: Path, basename: str, fields: tuple[str, ...]) -> dict[str, Any] | None:
    path = result / f"{basename}_rerun.json"
    if not path.is_file():
        path = result / f"{basename}.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or any(
        type(document.get(field)) is not bool for field in fields
    ):
        raise ValueError(f"malformed native judge verdict: {path.name}")
    return {field: document[field] for field in fields}


def _copy_evidence(result: Path, destination: Path) -> tuple[list[dict[str, Any]], bool]:
    destination.mkdir(parents=True, exist_ok=True)
    used = 0
    items = []
    truncated = False
    for name in EVIDENCE_FILES:
        source = result / name
        if not source.is_file() or source.is_symlink():
            continue
        size = source.stat().st_size
        if used + size > EVIDENCE_LIMIT:
            truncated = True
            continue
        target = destination / name
        shutil.copyfile(source, target)
        used += size
        items.append({"path": name, "size_bytes": size, "sha256": _sha256(target)})
    return items, truncated


def finalize(request: Request, result: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    evidence, evidence_truncated = _copy_evidence(result, output / "evidence")
    metrics_path = result / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
    accuracy = metrics.get("accuracy")
    if not isinstance(accuracy, (int, float)) or isinstance(accuracy, bool):
        accuracy = None

    contamination = _judgement(result, "judgement_gpt5_4", ("contamination", "disallowed_model"))
    api = _judgement(result, "judgement_api", ("disallowed_api_usage",))
    lookup = _judgement(result, "judgement_ptb_lookup", ("disallowed_ptb_lookup",))
    general = _judgement(result, "judgement_general", ("general_anomaly",))
    judges_complete = contamination is not None and api is not None and lookup is not None
    disqualified = bool(
        contamination
        and (contamination["contamination"] or contamination["disallowed_model"])
        or api
        and api["disallowed_api_usage"]
        or lookup
        and lookup["disallowed_ptb_lookup"]
    )

    model = None
    model_error = None
    try:
        store = (
            Path(request.model_store).resolve() if request.model_store else output / "model-store"
        )
        model = freeze_model(result / "final_model", store, request.max_model_bytes)
        _write_once(output / "model-handoff.json", model)
    except (OSError, ValueError) as error:
        model_error = type(error).__name__

    complete = accuracy is not None and judges_complete and model is not None
    protocol = (
        "engineering_valid"
        if complete and request.mode == "engineering"
        else "native_valid"
        if complete and not disqualified
        else "invalid"
        if disqualified
        else "review_required"
    )
    document = {
        "benchmark": "PostTrainBench",
        "upstream_revision": REVISION,
        "mode": request.mode,
        "task": request.task,
        "agent": request.agent,
        "agent_config": request.agent_config,
        "model_to_train": request.model_to_train,
        "budget": {"hours": request.num_hours, "gpus": request.num_gpus},
        "evaluation": "scored" if accuracy is not None else "failed",
        "protocol": protocol,
        "raw_metrics": metrics,
        "raw_accuracy": accuracy,
        "score_eligible": complete and not disqualified and request.mode == "native",
        "judges": {
            "contamination": contamination,
            "api_usage": api,
            "ptb_lookup": lookup,
            "general": general,
        },
        "model_handoff": model,
        "model_handoff_error": model_error,
        "evidence": evidence,
        "evidence_truncated": evidence_truncated,
        "official": False,
        "submission": "not_requested",
    }
    _write_once(output / "native-result.json", document)
    return document
