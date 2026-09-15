"""Private helpers shared by command-line Agent adapters."""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from agent_infra.agents.api import AgentProbe

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run_command(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    timeout = 600 if tuple(argv[:3]) == ("npm", "install", "--global") else 10
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def probe_npm_cli(
    *,
    provider: str,
    binary: str,
    npm_package: str,
    runner: CommandRunner,
    auth_args: tuple[str, ...] | None,
    container_config_reusable: bool,
) -> AgentProbe:
    executable = shutil.which(binary)
    if executable is None:
        return AgentProbe(
            provider=provider,
            available=False,
            executable=None,
            version=None,
            authenticated=None,
            container_auth_reusable=False,
            issues=(f"{provider} CLI is not installed or is not on PATH.",),
            install_command=("npm", "install", "--global", npm_package),
        )

    issues: list[str] = []
    version = _read_version(executable, runner, issues)
    authenticated = _read_auth_status(executable, auth_args, runner, issues)
    if authenticated is False:
        issues.append(f"{provider} login or model credentials are required.")
    reusable = container_config_reusable and authenticated is not False
    if authenticated and not reusable:
        issues.append(f"{provider} host credentials cannot currently be copied into a container.")
    return AgentProbe(
        provider=provider,
        available=True,
        executable=executable,
        version=version,
        authenticated=authenticated,
        container_auth_reusable=reusable,
        issues=tuple(issues),
    )


def ensure_npm_cli(
    probe: Callable[[], AgentProbe],
    runner: CommandRunner,
    *,
    install_spec: str | None = None,
    expected_version: str | None = None,
) -> AgentProbe:
    current = probe()
    if current.available and (expected_version is None or current.version == expected_version):
        return current
    install_command = current.install_command
    if install_command is None:
        if install_spec is None:
            raise RuntimeError(f"{current.provider} has an incompatible installed version")
        install_command = ("npm", "install", "--global", install_spec)
    try:
        result = runner(install_command)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"{current.provider} installation failed: {type(error).__name__}"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "npm failed"
        raise RuntimeError(f"{current.provider} installation failed: {detail}")
    installed = probe()
    if not installed.available:
        raise RuntimeError(f"{current.provider} was installed but is still not available on PATH")
    if expected_version is not None and installed.version != expected_version:
        raise RuntimeError(
            f"{current.provider} {expected_version} was requested, "
            f"but {installed.version!r} is active"
        )
    return installed


def stage_private_files(
    *, source_home: Path, destination: Path, filenames: tuple[str, ...]
) -> Path:
    if destination.is_symlink():
        raise ValueError("credential_home must not be a symbolic link")
    sources = [source_home / filename for filename in filenames]
    unavailable = [source for source in sources if not source.is_file() or source.is_symlink()]
    if unavailable:
        missing = ", ".join(source.name for source in unavailable)
        raise FileNotFoundError(
            f"required Agent credential/config files are unavailable: {missing}"
        )

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(stat.S_IRWXU)
    for source in sources:
        target = destination / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"credential target already exists: {target.name}")
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return destination


def _read_version(executable: str, runner: CommandRunner, issues: list[str]) -> str | None:
    try:
        result = runner([executable, "--version"])
    except (OSError, subprocess.SubprocessError) as error:
        issues.append(f"Unable to read CLI version: {type(error).__name__}.")
        return None
    if result.returncode != 0:
        issues.append("CLI version command failed.")
        return None
    match = re.search(r"(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)", result.stdout)
    return match.group(1) if match else result.stdout.strip() or None


def _read_auth_status(
    executable: str,
    auth_args: tuple[str, ...] | None,
    runner: CommandRunner,
    issues: list[str],
) -> bool | None:
    if auth_args is None:
        issues.append("This provider has no side-effect-free generic authentication probe.")
        return None
    try:
        result = runner([executable, *auth_args])
    except (OSError, subprocess.SubprocessError) as error:
        issues.append(f"Unable to check CLI authentication: {type(error).__name__}.")
        return None
    return result.returncode == 0
