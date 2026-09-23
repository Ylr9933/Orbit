"""Read-only validation and hashing of the pinned upstream checkout."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path

from agent_infra.contracts.files import content_digest

from .request import REVISION

SAFE_VALUE = re.compile(r"^[A-Za-z0-9._/+:[\]-]+$")
TASKS = Path("src/eval/tasks")
PROTOCOL_PATHS = (
    Path("src/run_task.sh"),
    Path("src/eval/general"),
    Path("src/eval/templates"),
    Path("src/judges"),
    Path("src/commit_utils/single_task.sub"),
    Path("scripts/collect.py"),
    Path("scripts/utils.py"),
    Path("scripts/baselines.json"),
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError("PostTrainBench Git checkout cannot be verified")
    return result.stdout.strip()


def checkout_root(source: Path) -> Path:
    source = source.resolve()
    anchor = source if source.is_dir() else source.parent
    root = Path(git(anchor, "rev-parse", "--show-toplevel")).resolve()
    if git(root, "rev-parse", "HEAD") != REVISION:
        raise ValueError("unsupported PostTrainBench checkout revision")
    return root


def task_identity(source: Path) -> tuple[Path, str]:
    source = source.resolve()
    root = checkout_root(source)
    try:
        relative = source.relative_to(root / TASKS)
    except ValueError as error:
        raise ValueError("source must be one PostTrainBench evaluation task") from error
    if len(relative.parts) != 1 or not (source / "evaluate.py").is_file():
        raise ValueError("source must be one PostTrainBench evaluation task")
    required = ("benchmark.txt", "evaluate.py", "info.json")
    if any(not (source / name).is_file() for name in required):
        raise ValueError("PostTrainBench task is incomplete")
    ensure_clean(root, (*PROTOCOL_PATHS, TASKS / relative))
    return root, relative.name


def ensure_clean(root: Path, paths: tuple[Path, ...]) -> None:
    changes = git(root, "status", "--porcelain", "--untracked-files=no", "--", *(map(str, paths)))
    if changes:
        raise ValueError("tracked PostTrainBench protocol files changed")


def runner_digest(root: Path) -> str:
    return tracked_digest(root, PROTOCOL_PATHS)


def tracked_digest(root: Path, paths: tuple[Path, ...]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", *(map(str, paths))],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("PostTrainBench tracked files cannot be enumerated")
    relatives = [Path(item.decode()) for item in result.stdout.split(b"\0") if item]
    if not relatives:
        raise ValueError("PostTrainBench digest scope has no tracked files")
    digest = hashlib.sha256()
    for relative in sorted(relatives):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("PostTrainBench digest scope contains a non-regular file")
        digest.update(relative.as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def task_digest(source: Path) -> str:
    root = checkout_root(source)
    return tracked_digest(root, (source.resolve().relative_to(root),))


def validate_agent(root: Path, agent: str) -> None:
    if not SAFE_VALUE.fullmatch(agent) or "/" in agent or agent in {".", ".."}:
        raise ValueError("invalid PostTrainBench agent name")
    directory = root / "agents" / agent
    required = (directory / "solve.sh", directory / "api_keys.json")
    if any(not item.is_file() for item in required):
        raise ValueError("agent is not present in the pinned PostTrainBench checkout")
    ensure_clean(root, tuple(item.relative_to(root) for item in required))
    document = json.loads(required[1].read_text(encoding="utf-8"))
    keys = document.get("allowed_api_keys")
    if not isinstance(keys, list) or not all(isinstance(item, str) for item in keys):
        raise ValueError("agent API-key allowlist is invalid")


def private_file(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("native configuration must be an absolute regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("native configuration must be owner-only")


def scheduler_digest(directory: Path) -> str:
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("scheduler_bin_dir must be an absolute regular directory")
    digest = hashlib.sha256()
    for name in ("condor_submit", "condor_q", "condor_history", "condor_rm"):
        path = directory / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_mode & stat.S_IXUSR:
            raise ValueError(f"scheduler command is unavailable: {name}")
        digest.update(name.encode())
        digest.update(content_digest(path).encode())
    return "sha256:" + digest.hexdigest()


def parse_env_path(path: Path, key: str, checkout: Path) -> Path:
    private_file(path)
    value = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, candidate = line.split("=", 1)
        if name.strip() == key:
            value = candidate.strip().strip('"').strip("'")
    if not value:
        raise ValueError(f"{key} is missing from private PostTrainBench configuration")
    result = Path(value).expanduser()
    return result.resolve() if result.is_absolute() else (checkout / result).resolve()
