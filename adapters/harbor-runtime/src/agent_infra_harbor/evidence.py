"""Inventory native evidence without inventing trajectories or silently dropping files."""

import hashlib
import json
from pathlib import Path


def inventory(root: Path, agent: str) -> dict:
    files = []
    unsafe = []
    for path in sorted((root / "trials").rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            unsafe.append(relative)
            continue
        if not path.is_file():
            continue
        if path.name in {"auth.json", ".env"}:
            raise ValueError("credential-shaped file in native outputs; refusing collection")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        files.append(
            {
                "member": "outputs/" + relative,
                "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    paths = [f["member"] for f in files]
    groups = {
        "native_sessions": [p for p in paths if "/agent/" in p and p.endswith(".jsonl")],
        "atif": [p for p in paths if "/agent/" in p and p.endswith("/trajectory.json")],
        "agent_logs": [p for p in paths if "/agent/" in p],
        "submission": [p for p in paths if "/artifacts/" in p],
        "verifier": [p for p in paths if "/verifier/" in p],
        "result": [p for p in paths if p.endswith("/result.json")],
    }
    required = ["result", "verifier"] + (["native_sessions", "atif"] if agent == "codex" else [])
    missing = [name for name in required if not groups[name]]
    result = {
        "schema_version": 1,
        "agent": agent,
        "files": {entry["member"]: entry for entry in files},
        "groups": groups,
        "missing": missing,
        "unsafe_paths": unsafe,
        "capture_status": "complete" if not missing and not unsafe else "incomplete",
        "scope": "native exported files; not a container syscall audit",
    }
    result["coverage"] = {
        name: "available" if members else "unavailable" for name, members in groups.items()
    }
    result["trajectory"] = trajectory_view(root, groups)
    result["calls"] = {
        "capture_status": "native_atif" if result["trajectory"].get("metrics") else "unavailable",
        "last_reported_usage": result["trajectory"].get("metrics"),
    }
    attestations = []
    for path in sorted((root / "attestations").glob("*-resources.json")):
        if not path.is_symlink():
            attestations.append(json.loads(path.read_bytes()))
    containers = [
        c for phase in attestations for c in phase["containers"] if c["service"] == "main"
    ]
    first = containers[0] if containers else {}
    result["docker"] = {
        "identity_status": "native_inspected" if containers else "unavailable",
        "container_id": first.get("id"),
        "image_id": first.get("image"),
        "cpu_limit": first.get("nano_cpus"),
        "memory_limit_bytes": first.get("memory_bytes"),
        "phases": attestations,
        "usage_status": "not_sampled",
    }
    (root / "native-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def trajectory_view(root: Path, groups: dict) -> dict:
    """Render bounded ATIF steps for the shared UI; native files remain lossless."""
    candidates = groups["atif"]
    if len(candidates) != 1:
        return {"capture_status": "unavailable", "total_steps": 0}
    source = root / candidates[0].removeprefix("outputs/")
    if source.stat().st_size > 64 * 1024**2:
        return {"capture_status": "too_large", "total_steps": 0}
    try:
        native = json.loads(source.read_bytes())
        if not isinstance(native, dict):
            raise ValueError("ATIF must be an object")
        steps = native["steps"]
        if not isinstance(steps, list):
            raise ValueError("ATIF steps must be a list")
        view = []
        clipped = 0
        for index, step in enumerate(steps[:2000]):
            if not isinstance(step, dict):
                raise ValueError("ATIF steps must be objects")
            content = json.dumps(
                {key: step[key] for key in ("message", "tool_calls", "observation") if key in step},
                ensure_ascii=False,
            )
            clipped += len(content) > 4000
            view.append(
                {
                    "step_index": index,
                    "timestamp_ms": None,
                    "step_type": step.get("source", "unknown"),
                    "content": content[:4000],
                    "metadata": {"role": step.get("source", "unknown")},
                }
            )
        output = root / "evidence"
        output.mkdir(exist_ok=True)
        (output / "trajectory-view.json").write_text(json.dumps(view, ensure_ascii=False))
        return {
            "capture_status": "truncated" if clipped or len(steps) > 2000 else "complete",
            "total_steps": len(steps),
            "view_steps": len(view),
            "content_truncated_steps": clipped,
            "member": "outputs/evidence/trajectory-view.json",
            "origin": "native_harbor_atif",
            "session_id": native.get("session_id"),
            "metrics": {
                key: value
                for key, value in (native.get("final_metrics") or {}).items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            },
        }
    except (ValueError, KeyError, TypeError):
        return {"capture_status": "invalid", "total_steps": 0}
