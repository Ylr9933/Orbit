"""Optional immutable local Codex distribution; native Harbor still runs the agent."""

from pathlib import Path

from agent_infra.contracts.files import content_digest
from agent_infra.environments.recovery import write_ownership


def validate_bundle(path: str, digest: str) -> Path:
    source = Path(path)
    if not source.is_absolute() or any(
        not (source / member).is_file() for member in ("bin/codex", "codex-path/rg")
    ):
        raise ValueError(
            "codex_bundle must be an absolute native distribution with bin/codex and codex-path/rg"
        )
    if content_digest(source) != digest:
        raise ValueError("Codex bundle changed after preparation")
    return source


async def install(environment, path: str, digest: str, version: str, evidence: Path) -> None:
    source = validate_bundle(path, digest)
    target = "/opt/agent-infra-codex"
    await environment.upload_dir(source, target)
    result = await environment.exec(
        command=(
            "chmod +x /opt/agent-infra-codex/bin/* /opt/agent-infra-codex/codex-path/rg && "
            "ln -sf /opt/agent-infra-codex/bin/codex /usr/local/bin/codex && "
            "ln -sf /opt/agent-infra-codex/codex-path/rg /usr/local/bin/rg && "
            "/usr/local/bin/codex --version"
        ),
        user="root",
    )
    actual = (result.stdout or "").strip().removeprefix("codex-cli ")
    if result.return_code != 0 or actual != version:
        raise RuntimeError("Codex bundle is incompatible with container OS/architecture/version")
    write_ownership(
        evidence,
        {"source_digest": digest, "version": actual, "install_method": "local_native_distribution"},
    )
