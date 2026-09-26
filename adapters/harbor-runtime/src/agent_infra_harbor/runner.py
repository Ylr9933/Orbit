"""One native Harbor trial in a durable, process-owned working directory."""

import asyncio
import signal
import sys
import uuid
from pathlib import Path

from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from agent_infra.contracts.files import content_digest
from agent_infra.environments.recovery import write_ownership

from . import environment
from .agent import configuration as agent_configuration
from .docker import remaining
from .evidence import inventory
from .proxy import SolverProxy
from .request import Request


async def run(request: Request) -> int:
    root = Path.cwd()
    owner = uuid.uuid4().hex[:24]
    environment.CONTEXT.update(
        root=str(root),
        owner=owner,
        cpu=request.cpu,
        memory_mb=request.memory_mb,
        task=request.task,
        codex_bundle=request.codex_bundle,
        codex_bundle_digest=request.codex_bundle_digest,
        codex_version=request.codex_version,
    )
    code = 1
    relay = None
    try:
        if content_digest(Path(request.task)) != request.task_digest:
            raise ValueError("task snapshot changed after planning")
        if request.proxy_url:
            relay = SolverProxy(request.proxy_url)
            await relay.start()
            environment.CONTEXT["relay"] = relay
        configuration = {
            "task": {"path": request.task},
            "trial_name": "infra_" + owner,
            "trials_dir": str(root / "trials"),
            "agent": agent_configuration(request),
            "environment": {
                "import_path": "agent_infra_harbor.environment:OwnedDockerEnvironment",
            },
        }
        if relay:
            configuration["agent"]["env"].update(
                {
                    key: relay.url
                    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
                }
            )
        if request.source_trial:
            configuration["source_trial"] = {
                "action": "regrade",
                "type": "local",
                "path": request.source_trial,
            }
        trial = await Trial.create(TrialConfig.model_validate(configuration))
        write_ownership(
            root / "native-job.json",
            {
                "trial_id": str(trial.id),
                "trial_name": configuration["trial_name"],
                "request": request.model_dump(),
            },
        )

        async def log(entry):
            print(entry.model_dump_json(), flush=True)

        trial.add_log_callback(log)
        current = asyncio.current_task()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, current.cancel)
        result = await trial.run()
        code = 0 if result.exception_info is None else 1
        print(result.model_dump_json(), flush=True)
    except asyncio.CancelledError:
        code = 130
    finally:
        complete = False
        try:
            await environment.close_all()
            complete = all(
                not env.launch_uncertain and not remaining(env.project)
                for env in environment.ENVIRONMENTS
            )
        finally:
            if relay:
                await relay.close()
            write_ownership(
                root / "native-cleanup.json",
                {
                    "complete": complete,
                    "projects": [env.project for env in environment.ENVIRONMENTS],
                },
            )
            inventory(root, request.agent)
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(run(Request.model_validate_json(sys.argv[1]))))
