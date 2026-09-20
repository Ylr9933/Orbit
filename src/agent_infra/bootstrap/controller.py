"""Local daemon composition. Projects, providers and Docker meet only here."""

import argparse
import json
import os
import secrets
import signal
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_infra.bootstrap.host_research import import_host_trace, project_context
from agent_infra.bootstrap.iteration import StudyActions
from agent_infra.bootstrap.run_preflight import prepare_compiled_run
from agent_infra.environments import planner_client as planner_helper
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.environments.model_proxy import ModelProxyRelay, model_connection
from agent_infra.environments.preparation_docker import DockerEnvironmentPreparer
from agent_infra.environments.preparation_store import EnvironmentCatalog
from agent_infra.environments.recovery import inspect_local_image, recover_owned_containers
from agent_infra.environments.research import DockerResearchEnvironment
from agent_infra.gateways.cli.environment import environment_client
from agent_infra.gateways.cli.research_runtime import research_client
from agent_infra.gateways.cli.runs import run_client
from agent_infra.gateways.cli.study import planner_client, study_client
from agent_infra.gateways.http.control import create_control_server
from agent_infra.gateways.mcp.research import serve_mcp
from agent_infra.records.local import LocalRecordsStore
from agent_infra.resources import LinuxHostResourceMonitor, LocalResourceManager, NodeCapacity
from agent_infra.runs.control_api import PreparedRun, SubmissionRequest
from agent_infra.runs.control_store import RunControlStore
from agent_infra.runs.controller import LocalRunController
from agent_infra.runs.environment_preparation import EnvironmentPreparation
from agent_infra.runs.host_lock import HostControllerLock
from agent_infra.runs.planner import PlannerSessions
from agent_infra.runs.query import RunQueries
from agent_infra.runs.research import ResearchController
from agent_infra.runs.research_store import ResearchStore
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
    if args.command == "planner":
        return planner_client(state, args)
    if args.command == "study":
        return study_client(state, args)
    if args.command == "run":
        return run_client(state, args)
    if args.command == "environment":
        return environment_client(state, args)
    if args.command == "research":
        return research_client(state, args)
    if args.command == "mcp":
        serve_mcp(state, args.project_id, args.session_id)
        return 0
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
    research: ResearchController | None = None
    preparation: EnvironmentPreparation | None = None
    planner: PlannerSessions | None = None
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
        preparation = EnvironmentPreparation(
            controller,
            EnvironmentCatalog(root / "preparation"),
            DockerEnvironmentPreparer(environment),
        )
        study = StudyActions(state, controller, RunQueries(controller.store, records))
        research = ResearchController(
            controller,
            ResearchStore(root),
            DockerResearchEnvironment(environment),
            records,
            lambda identifier: project_context(state, identifier),
            inspect_local_image,
            import_host_trace,
            preparation,
            study.call,
        )
        planner = PlannerSessions(
            controller,
            environment,
            study.planner_call,
            Path(planner_helper.__file__),
            lambda image: inspect_local_image(image, provider="codex"),
            connection,
        )
        token = secrets.token_urlsafe(32)
        server = create_control_server(
            controller,
            RunQueries(controller.store, records),
            token,
            port,
            research=research,
            planner=planner,
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
        planner_clean = planner.close() if planner is not None else True
        preparation_clean = preparation.close() if preparation is not None else True
        research_clean = research.close() if research is not None else True
        if controller is not None:
            clean = controller.close() and research_clean and preparation_clean and planner_clean
            endpoint.unlink(missing_ok=True)
        if relay is not None:
            relay.close()
        lock.close(clean=clean)
