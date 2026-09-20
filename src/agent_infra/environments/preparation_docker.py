"""Fixed Python template and independent smoke, using the existing owned Docker runtime."""

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Any

from agent_infra.contracts.files import resolve_material
from agent_infra.environments.api import EnvironmentHandle, LogCursor, ProcessCommand, SandboxSpec
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.preparation_api import (
    EnvironmentIntent,
    EnvironmentProposal,
    PreparationResult,
)
from agent_infra.environments.recovery import inspect_local_image

# These are trusted product instructions. No model-generated code is evaluated here.
_INSTALL = """import importlib.metadata as m, json, pathlib, subprocess, sys
requirements = json.load(sys.stdin)
if requirements:
    subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
        'install', '--no-cache-dir', '--only-binary=:all:', '--index-url', 'https://pypi.org/simple',
        '--report', '/workspace/pip-report.json', *requirements], check=True)
report = pathlib.Path('/workspace/pip-report.json')
resolved = []
if report.exists():
    for item in json.loads(report.read_text())['install']:
        resolved.append({'name': item['metadata']['name'], 'version': item['metadata']['version'],
            'hashes': item['download_info'].get('archive_info', {}).get('hashes', {})})
pathlib.Path('/workspace/packages.json').write_text(json.dumps({
    'installed': sorted([{'name': d.metadata['Name'], 'version': d.version}
                         for d in m.distributions()], key=lambda d: d['name']),
    'resolved': resolved, 'python': sys.version}))
"""

_SMOKE = """import importlib, importlib.metadata as m, json, pathlib, subprocess, sys
config = json.load(sys.stdin)
for module in config['imports']:
    importlib.import_module(module)
for requirement in config['dependencies']:
    name, version = requirement.split('==')
    if m.version(name) != version:
        raise RuntimeError('dependency version mismatch: ' + name)
p = pathlib.Path('/workspace/outputs')
p.mkdir()
(p / 'smoke.txt').write_text('ready')
if (p / 'smoke.txt').read_text() != 'ready':
    raise RuntimeError('workspace output readback failed')
if config['agent'] == 'codex':
    version = subprocess.check_output(['codex', '--version'], text=True, timeout=10).strip()
    if version != 'codex-cli 0.154.0':
        raise RuntimeError('expected codex-cli 0.154.0, found ' + version)
print(json.dumps({'ready': True, 'imports': config['imports'],
                  'agent': config['agent']}), flush=True)
"""


class DockerEnvironmentPreparer:
    def __init__(self, environment: DockerEnvironment) -> None:
        self.environment = environment

    def resolve(self, image: str, agent: str = "none") -> str:
        return inspect_local_image(image, provider="codex" if agent == "codex" else None)

    def execute(
        self,
        *,
        key: str,
        intent: EnvironmentIntent,
        proposal: EnvironmentProposal,
        base: str,
        cached: dict[str, Any] | None,
        workspace: Path,
        timeout: float,
        cancel: Event,
        emit: Callable[[str, dict[str, Any]], None],
    ) -> PreparationResult:
        deadline = time.monotonic() + timeout
        handles: list[EnvironmentHandle] = []
        details: dict[str, Any] = {"cache_hit": False, "template": intent.template}
        image: str | None = None
        status = "failed"
        cleanup = True
        try:
            if cached:
                try:
                    image = self.resolve(cached["image_id"], intent.agent)
                    details.update(cache_hit=True, packages=cached.get("packages", {}))
                except (RuntimeError, ValueError):
                    emit("cache.miss", {"reason": "cached image is unavailable"})
            if image is None and intent.template == "existing":
                image = self.resolve(base, intent.agent)
            if image is None:
                build = workspace / "build"
                build.mkdir(parents=True, mode=0o700)
                # Build runs as UID 0 with all capabilities dropped; its empty output
                # directory must be writable. The enclosing state remains private.
                build.chmod(0o777)
                handle = self.environment.prepare(
                    SandboxSpec(
                        workspace.name + ":build",
                        "build",
                        base,
                        build,
                        intent.cpu,
                        intent.memory_bytes,
                        network=intent.network,
                    )
                )
                handles.append(handle)
                emit("build.started", {"environment_id": handle.id, "base_image_id": base})
                self._process(
                    handle, _INSTALL, list(proposal.dependencies), deadline, cancel, emit, "build"
                )
                packages = resolve_material(build, "packages.json")
                if packages.stat().st_size > 1024**2:
                    raise ValueError("package inventory exceeds 1 MiB")
                details["packages"] = json.loads(packages.read_text())
                self._check(deadline, cancel)
                image = self.environment.publish_build(handle, key)
                emit("image.published", {"image_id": image})
                # Remove the build container before reserving memory for independent smoke.
                result = self.environment.cleanup(handle)
                if not result.complete:
                    raise RuntimeError("build cleanup failed")
                self._check(deadline, cancel)
            smoke = workspace / "smoke"
            smoke.mkdir(parents=True, mode=0o700)
            handle = self.environment.prepare(
                SandboxSpec(
                    workspace.name + ":smoke",
                    "solver",
                    image,
                    smoke,
                    intent.cpu,
                    intent.memory_bytes,
                )
            )
            handles.append(handle)
            emit("smoke.started", {"environment_id": handle.id, "image_id": image})
            self._process(
                handle,
                _SMOKE,
                {
                    "imports": intent.imports,
                    "dependencies": proposal.dependencies,
                    "agent": intent.agent,
                },
                deadline,
                cancel,
                emit,
                "smoke",
            )
            status = "ready"
        except InterruptedError:
            status = "cancelled"
        except TimeoutError:
            status = "timed_out"
        except Exception as error:
            details["error"] = str(error)
        finally:
            for handle in reversed(handles):
                result = self.environment.cleanup(handle)
                cleanup = cleanup and result.complete
            if not cleanup:
                status = "cleanup_failed"
        return PreparationResult(status, image, cleanup, details)

    @staticmethod
    def _check(deadline: float, cancel: Event) -> None:
        if cancel.is_set():
            raise InterruptedError
        if time.monotonic() >= deadline:
            raise TimeoutError

    def _process(
        self,
        handle: EnvironmentHandle,
        script: str,
        config: Any,
        deadline: float,
        cancel: Event,
        emit: Callable[[str, dict[str, Any]], None],
        phase: str,
    ) -> None:
        self._check(deadline, cancel)
        self.environment.start(
            handle,
            ProcessCommand(
                ("python3", "-I", "-u", "-c", script),
                stdin_text=json.dumps(config),
                timeout_seconds=max(0.01, deadline - time.monotonic()),
            ),
        )
        cursor = LogCursor()
        while True:
            self._check(deadline, cancel)
            observation = self.environment.observe(handle, cursor)
            cursor = observation.cursor
            if observation.stdout or observation.stderr:
                emit(phase + ".output", asdict(observation))
            if observation.status not in {"prepared", "running"}:
                # Drain beyond the final 64 KiB page before judging completion.
                if observation.stdout or observation.stderr:
                    continue
                if observation.status == "timed_out":
                    raise TimeoutError
                if observation.status != "exited" or observation.exit_code != 0:
                    raise ValueError(
                        f"{phase} failed ({observation.status}, exit={observation.exit_code}); "
                        "inspect environment logs"
                    )
                return
            cancel.wait(0.15)
