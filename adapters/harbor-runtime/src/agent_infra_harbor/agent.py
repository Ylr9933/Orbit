"""Explicit native Agent configuration; credentials never enter frozen requests."""

import os
import pwd
from pathlib import Path

from .request import Request


def configuration(request: Request) -> dict:
    if request.agent != "codex":
        return {"name": request.agent}
    # Disallow ambient Codex behavior/configuration inherited from the developer session.
    for key in tuple(os.environ):
        if key.startswith("CODEX_") or key in {"OPENAI_BASE_URL", "OPENAI_API_BASE"}:
            os.environ.pop(key, None)
    env = {}
    if request.auth_mode == "host_codex":
        auth = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codex/auth.json"
        if not auth.is_file() or auth.is_symlink() or auth.stat().st_uid != os.getuid():
            raise ValueError("host_codex requires an owned, regular ~/.codex/auth.json")
        env["CODEX_AUTH_JSON_PATH"] = str(auth)
        os.environ.pop("OPENAI_API_KEY", None)
    else:
        key_file = Path(request.api_key_file)
        if (
            not key_file.is_absolute()
            or key_file.is_symlink()
            or not key_file.is_file()
            or key_file.stat().st_uid != os.getuid()
            or key_file.stat().st_mode & 0o077
        ):
            raise ValueError("api_key_file must be an owned private regular file (0600)")
        if key_file.stat().st_size > 65536:
            raise ValueError("api_key_file is too large")
        secret = key_file.read_text().strip()
        if not secret or "\n" in secret:
            raise ValueError("api_key_file must contain one nonempty key")
        os.environ["OPENAI_API_KEY"] = secret
    return {
        "name": "codex",
        "model_name": request.model,
        "kwargs": {"version": request.codex_version, "reasoning_effort": request.effort},
        "env": env,
    }
