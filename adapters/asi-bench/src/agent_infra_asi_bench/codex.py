"""Explicit native Codex/Docker OS profile; fixture compatibility stays intact."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from agent_infra.benchmarks.api import AdapterDescriptor, ExecutionPlan, ResourceRequirements

from . import Adapter
from .backend import CodexAsiBenchBackend
from .request import FEATURES

CODEX_FEATURES = FEATURES + ("docker_os", "native_codex_trace", "docker_telemetry")


class CodexAdapter(Adapter):
    descriptor = AdapterDescriptor(
        adapter_id="asi-bench-codex-os",
        description="Pinned ASI-Bench public Codex CLI with native Docker OS sandbox",
    )
    profile = "seed31415-single-codex-os-v1"
    mode = "codex_os"
    required_features = CODEX_FEATURES
    resources = ResourceRequirements(
        cpu_cores=4, memory_bytes=8 * 1024**3, gpu_count=0, allocator="local"
    )
    allowed_parameters = Adapter.allowed_parameters | {"effort", "proxy_url", "docker_network"}
    limitations = (
        "One public seed31415 instance; local score is non-official",
        "Native ASI-Bench Docker OS sandbox owns Codex and its task image",
        "Docker OS defaults to 4 CPU/8 GiB; no GPU or complete-suite claim",
        "Private seed42 submission remains a separate native protocol",
    )

    def _validate_candidate(self, plan: ExecutionPlan, params: dict[str, str]) -> None:
        candidate = plan.request.candidate
        if candidate.agent != "codex_cli" or candidate.agent_version != "asibench-0.1.5":
            raise ValueError("Codex OS profile requires native codex_cli from ASI-Bench 0.1.5")
        if candidate.model in {"", "none"}:
            raise ValueError("Codex OS profile requires an explicit model")
        if params.get("effort", "medium") not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("unsupported Codex reasoning effort")
        network = params.get("docker_network", "bridge")
        if network not in {"bridge", "host"}:
            raise ValueError("unsupported Docker network mode")
        proxy = params.get("proxy_url", "")
        if proxy:
            parsed = urlsplit(proxy)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("proxy_url must be an unauthenticated HTTP(S) origin")
            if parsed.hostname in {"127.0.0.1", "localhost"} and network != "host":
                raise ValueError("loopback proxy requires docker_network=host")

    def _extra_outputs(self) -> tuple[str, ...]:
        return ("evidence", "docker-observations.jsonl")

    def _artifact_limit(self) -> int:
        return 256 * 1024**2

    def execution_backend(self, root: Path) -> CodexAsiBenchBackend:
        return CodexAsiBenchBackend(root)

    def _interpret_evidence(self, root: Path) -> dict:
        index = root / "outputs" / "evidence" / "index.json"
        if not index.is_file():
            return {"evidence": {"capture_status": "unavailable"}}
        value = json.loads(index.read_text(encoding="utf-8"))
        return {
            "evidence": {
                "capture_status": value["capture_status"],
                "files": value["files"],
                "calls": value.get("calls", {}),
                "trajectory": value.get("trajectory", {}),
                "docker": value.get("docker", {}),
            }
        }

    def interpret(self, root: Path) -> dict:
        result = super().interpret(root)
        if "evidence" not in result:
            result.update(self._interpret_evidence(root))
        return result
