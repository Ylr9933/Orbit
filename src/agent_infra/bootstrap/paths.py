"""Shared state defaults and controller directory preparation; no IO on import."""

import os
from collections.abc import Mapping
from pathlib import Path


def state_root(value: str | None = None, *, environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = value if value is not None else env.get("AGENT_INFRA_STATE_DIR")
    if configured is None:
        # Resolve trusted user defaults: ~/.local is often relocated on research hosts.
        base = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        return (base / "agent-infra").expanduser().resolve()
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("state directory must be a non-empty path")
    path = Path(configured).expanduser()
    if ".." in path.parts:
        raise ValueError("parent traversal is not allowed in state paths")
    absolute = Path(os.path.abspath(path))
    # Do not silently resolve explicit paths that Project's pinned filesystem rejects.
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            raise ValueError("explicit state paths must not contain symlinks; use the real path")
    return absolute


def prepare_controller_root(state: Path) -> Path:
    """Create the private parent before Records/other stores create their children."""
    root = state / "controller"
    for part in (root, *root.parents):
        if part.is_symlink():
            raise ValueError("controller state paths must not contain symlinks")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError(
            f"controller state must be private and owned by this user: {root}; "
            "check ownership and set its permissions to 0700 before retrying"
        )
    return root
