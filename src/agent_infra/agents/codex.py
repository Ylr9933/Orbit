"""Codex CLI adapter for host research and isolated container runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from agent_infra.agents.api import (
    AgentCapability,
    AgentDescriptor,
    AgentEvent,
    AgentEventKind,
    AgentLaunchPlan,
    AgentPermissionMode,
    AgentPlacement,
    AgentProbe,
    AgentRunRequest,
    BindMount,
)

CODEX_PROVIDER = "codex"
DEFAULT_CODEX_IMAGE = "agent-infra/codex-cli:0.154.0"
CONTAINER_CODEX_HOME = "/home/agent/.codex"
CONTAINER_WORKSPACE = "/workspace"
CODEX_NPM_PACKAGE = "@openai/codex"
CODEX_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "ultra"})

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
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


class CodexAdapter:
    """Translate provider-neutral requests into Codex CLI process plans."""

    def __init__(
        self,
        *,
        binary: str = "codex",
        container_image: str = DEFAULT_CODEX_IMAGE,
        runner: CommandRunner = _default_runner,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._binary = binary
        self._container_image = container_image
        self._runner = runner
        self._environ = os.environ if environ is None else environ

    @property
    def descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            provider=CODEX_PROVIDER,
            display_name="OpenAI Codex CLI",
            integration="cli",
            capabilities=frozenset(
                {
                    AgentCapability.NON_INTERACTIVE,
                    AgentCapability.EVENT_STREAM,
                    AgentCapability.HOST_EXECUTION,
                    AgentCapability.CONTAINER_EXECUTION,
                }
            ),
        )

    def probe(self) -> AgentProbe:
        executable = shutil.which(self._binary)
        if executable is None:
            return AgentProbe(
                provider=CODEX_PROVIDER,
                available=False,
                executable=None,
                version=None,
                authenticated=None,
                container_auth_reusable=False,
                issues=("Codex CLI is not installed or is not on PATH.",),
                install_command=("npm", "install", "--global", CODEX_NPM_PACKAGE),
            )

        issues: list[str] = []
        version = self._read_version(executable, issues)
        authenticated = self._read_auth_status(executable, issues)
        if authenticated is False:
            issues.append("Codex login is required.")
        auth_file = self.host_codex_home / "auth.json"
        reusable = authenticated is True and auth_file.is_file()
        if authenticated and not reusable:
            issues.append(
                "Host authentication is not file-based; container reuse requires "
                "CODEX_HOME/auth.json."
            )
        return AgentProbe(
            provider=CODEX_PROVIDER,
            available=True,
            executable=executable,
            version=version,
            authenticated=authenticated,
            container_auth_reusable=reusable,
            issues=tuple(issues),
        )

    def ensure_installed(self) -> AgentProbe:
        """Install the official npm package only when Codex is absent."""

        current = self.probe()
        if current.available:
            return current
        assert current.install_command is not None
        try:
            result = self._runner(current.install_command)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"Codex installation failed: {type(error).__name__}") from error
        if result.returncode != 0:
            detail = (
                result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "npm failed"
            )
            raise RuntimeError(f"Codex installation failed: {detail}")
        installed = self.probe()
        if not installed.available:
            raise RuntimeError("Codex was installed but is still not available on PATH")
        return installed

    @property
    def host_codex_home(self) -> Path:
        configured = self._environ.get("CODEX_HOME")
        if configured:
            return Path(configured).expanduser()
        configured_home = self._environ.get("HOME")
        return (Path(configured_home) if configured_home else Path.home()) / ".codex"

    def stage_container_credentials(self, destination: Path) -> Path:
        """Copy only file-based auth into a task-owned Codex home."""

        source = self.host_codex_home / "auth.json"
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(
                "Codex file credentials are unavailable; sign in with file credential "
                "storage first."
            )
        if destination.is_symlink():
            raise ValueError("credential_home must not be a symbolic link")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.chmod(stat.S_IRWXU)
        target = destination / "auth.json"
        if target.exists() or target.is_symlink():
            raise FileExistsError("credential target already exists")
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return destination

    def create_launch_plan(
        self, request: AgentRunRequest, *, credential_home: Path | None = None
    ) -> AgentLaunchPlan:
        if not request.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not request.prompt.strip():
            raise ValueError("prompt must not be empty")
        if request.resume_session_id is not None:
            raise ValueError("Codex session resume is not implemented by this adapter")
        if (
            request.reasoning_effort is not None
            and request.reasoning_effort not in CODEX_REASONING_EFFORTS
        ):
            supported = ", ".join(sorted(CODEX_REASONING_EFFORTS))
            raise ValueError(f"unsupported Codex reasoning effort; choose one of: {supported}")
        if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX and (
            request.placement is not AgentPlacement.CONTAINER
        ):
            raise ValueError("outer_sandbox permission mode is valid only inside a container")

        runtime_workspace = (
            CONTAINER_WORKSPACE
            if request.placement is AgentPlacement.CONTAINER
            else str(request.workspace.resolve())
        )
        binary = "codex" if request.placement is AgentPlacement.CONTAINER else self._binary
        argv = [binary, "exec"]
        if request.model:
            argv.extend(["--model", request.model])
        if request.reasoning_effort:
            argv.extend(["--config", f'model_reasoning_effort="{request.reasoning_effort}"'])
        argv.extend(
            [
                "--cd",
                runtime_workspace,
                "--skip-git-repo-check",
                "--json",
                "--color",
                "never",
            ]
        )

        mounts: tuple[BindMount, ...] = ()
        environment: tuple[tuple[str, str], ...] = ()
        image: str | None = None
        if request.placement is AgentPlacement.CONTAINER:
            if credential_home is None:
                raise ValueError("container placement requires an isolated credential_home")
            if request.permission_mode is AgentPermissionMode.OUTER_SANDBOX:
                argv.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                argv.extend(["--sandbox", "workspace-write"])
            argv.extend(["--ignore-user-config", "--ignore-rules"])
            environment = (("CODEX_HOME", CONTAINER_CODEX_HOME),)
            mounts = (
                BindMount(credential_home.resolve(), CONTAINER_CODEX_HOME, read_only=False),
                BindMount(request.workspace.resolve(), CONTAINER_WORKSPACE, read_only=False),
            )
            image = self._container_image
        else:
            argv.extend(["--sandbox", "workspace-write"])

        argv.extend(["--", "-"])
        return AgentLaunchPlan(
            provider=CODEX_PROVIDER,
            placement=request.placement,
            argv=tuple(argv),
            cwd=runtime_workspace,
            stdin_text=request.prompt,
            environment=environment,
            mounts=mounts,
            container_image=image,
        )

    def decode_events(self, lines: Iterator[str]) -> Iterator[AgentEvent]:
        for sequence, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                yield AgentEvent(sequence, AgentEventKind.ERROR, "invalid_json", {"text": stripped})
                continue
            if not isinstance(payload, dict):
                yield AgentEvent(sequence, AgentEventKind.UNKNOWN, "unknown", {"value": payload})
                continue
            native_type = str(payload.get("type", "unknown"))
            yield AgentEvent(sequence, _event_kind(native_type, payload), native_type, payload)

    def _read_version(self, executable: str, issues: list[str]) -> str | None:
        try:
            result = self._runner([executable, "--version"])
        except (OSError, subprocess.SubprocessError) as error:
            issues.append(f"Unable to read Codex version: {type(error).__name__}.")
            return None
        if result.returncode != 0:
            issues.append("Codex version command failed.")
            return None
        match = re.search(r"(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)", result.stdout)
        return match.group(1) if match else result.stdout.strip() or None

    def _read_auth_status(self, executable: str, issues: list[str]) -> bool | None:
        try:
            result = self._runner([executable, "login", "status"])
        except (OSError, subprocess.SubprocessError) as error:
            issues.append(f"Unable to check Codex authentication: {type(error).__name__}.")
            return None
        return result.returncode == 0


def _event_kind(native_type: str, payload: dict[str, object]) -> AgentEventKind:
    lowered = native_type.lower()
    if "error" in lowered or lowered.endswith("failed"):
        return AgentEventKind.ERROR
    if "usage" in lowered:
        return AgentEventKind.USAGE
    if lowered.startswith("thread") or lowered.startswith("session"):
        return AgentEventKind.SESSION
    if "completed" in lowered and ("turn" in lowered or lowered == "completed"):
        return AgentEventKind.COMPLETED
    item = payload.get("item")
    item_type = str(item.get("type", "")) if isinstance(item, dict) else ""
    if (
        "tool" in lowered
        or "command" in lowered
        or item_type
        in {
            "command_execution",
            "mcp_tool_call",
        }
    ):
        return AgentEventKind.TOOL_RESULT if "completed" in lowered else AgentEventKind.TOOL_CALL
    if "message" in lowered or item_type in {"agent_message", "reasoning"}:
        return AgentEventKind.MESSAGE
    return AgentEventKind.UNKNOWN
