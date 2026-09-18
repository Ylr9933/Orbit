"""Local daemon composition. Projects, providers and Docker meet only here."""

import argparse
import json
import os
import secrets
import signal
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_infra.bootstrap.run_preflight import prepare_compiled_run
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.model_proxy import ModelProxyRelay, model_connection
from agent_infra.environments.recovery import recover_owned_containers
from agent_infra.gateways.cli.runs import run_client
from agent_infra.gateways.http.control import create_control_server
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources import LinuxHostResourceMonitor, LocalResourceManager, NodeCapacity
from agent_infra.runs.control_api import PreparedRun, SubmissionRequest
from agent_infra.runs.control_store import RunControlStore
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.host_lock import HostControllerLock
from agent_infra.runs.query import RunQueries
from agent_infra.runs.service import LocalRunService


def state_root(value: str | None) -> Path:
    configured = value or os.environ.get("AGENT_INFRA_STATE_DIR")
    return (
        Path(configured).expanduser()
        if configured
        else Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "agent-infra"
    ).resolve()


def run_action(args: argparse.Namespace) -> dict[str, Any] | int:
    state = state_root(args.state_dir)
    if args.command == "run":
        return run_client(state, args)
    return serve_controller(
        state,
        port=args.port,
        cpu=args.cpu,
        memory_bytes=int(args.memory_gib * 1024**3),
        proxy=args.model_proxy,
    )


def serve_controller(
    state: Path, *, port: int, cpu: float, memory_bytes: int, proxy: str = "auto"
) -> int:
    lock = HostControllerLock(state)
    controller: LocalRunController | None = None
    clean = False
    relay: ModelProxyRelay | None = None
    root = state / "controller"
    endpoint = root / "endpoint.json"
    previous_handler = signal.getsignal(signal.SIGTERM)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise ValueError("controller state must be a private directory owned by this user")
        monitor = LinuxHostResourceMonitor()
        snapshot = monitor.sample()
        # GPU admission is deliberately disabled until an explicit device allowlist is implemented.
        resources = LocalResourceManager(NodeCapacity(snapshot.node_id, cpu, memory_bytes))
        resources.update_snapshot(snapshot)
        records = LocalRecordsStore(root / "records")
        environment = DockerEnvironment(root / "environments")
        service = LocalRunService(
            environment, resources, root / "work", node_id=snapshot.node_id, records=records
        )
        connection, relay = model_connection(proxy)

        def prepare(request: SubmissionRequest) -> PreparedRun:
            prepared = prepare_compiled_run(state, request)
            return replace(
                prepared, request=replace(prepared.request, connection_environment=connection)
            )

        controller = LocalRunController(
            RunControlStore(root),
            service,
            records,
            resources,
            prepare,
            lambda: resources.update_snapshot(monitor.sample()),
            lambda: recover_owned_containers(root / "environments"),
        )
        token = secrets.token_urlsafe(32)
        server = create_control_server(
            controller, RunQueries(controller.store, records), token, port
        )
        with server:
            temporary = root / "endpoint.tmp"
            with temporary.open("w") as file:
                os.chmod(temporary, 0o600)
                json.dump({"port": server.server_port, "token": token, "pid": os.getpid()}, file)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(endpoint)
            print(
                json.dumps(
                    {
                        "controller": "ready",
                        "port": server.server_port,
                        "state_dir": str(state),
                        "cpu": cpu,
                        "memory_bytes": memory_bytes,
                    }
                ),
                flush=True,
            )

            def stop(signum: int, frame: Any) -> None:
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, stop)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
        return 0
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        if controller is not None:
            clean = controller.close()
            endpoint.unlink(missing_ok=True)
        if relay is not None:
            relay.close()
        lock.close(clean=clean)
