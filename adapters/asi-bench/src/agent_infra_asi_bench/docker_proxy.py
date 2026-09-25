"""Narrow Docker CLI proxy: label and sample only this ASI agent container."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OWNER_LABEL = "agent-infra.asi-run"


def summarize(observations: list[dict], image_id: str | None) -> dict:
    """Describe observed native limits and samples without claiming full coverage."""
    identity = next((item for item in observations if item.get("kind") == "identity"), {})
    samples = [
        item["sample"]
        for item in observations
        if item.get("kind") == "usage" and isinstance(item.get("sample"), dict)
    ]
    return {
        "container_id": identity.get("container_id"),
        "image_id": image_id,
        "cpu_limit": identity.get("cpu_limit"),
        "memory_limit_bytes": identity.get("memory_limit_bytes"),
        "identity_status": "attested" if identity else "unavailable",
        "usage_samples": len(samples),
        "usage_status": "sampled" if samples else "unavailable",
        "last_sample": samples[-1] if samples else None,
    }


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def main() -> int:
    docker = os.environ["AGENT_INFRA_DOCKER_BIN"]
    args = sys.argv[1:]
    if args and args[0] == "build" and os.environ.get("AGENT_INFRA_ASI_BUILD_NETWORK") == "host":
        os.execv(docker, [docker, "build", "--network", "host", *args[1:]])
    if len(args) < 2 or args[0] != "run" or "--name" not in args:
        os.execv(docker, [docker, *args])
    try:
        name = args[args.index("--name") + 1]
    except IndexError:
        os.execv(docker, [docker, *args])
    if not name.startswith("ai4sci-agent-"):
        os.execv(docker, [docker, *args])
    owner = os.environ["AGENT_INFRA_ASI_RUN"]
    path = Path(os.environ["AGENT_INFRA_DOCKER_OBSERVATIONS"])
    process = subprocess.Popen([docker, "run", "--label", f"{OWNER_LABEL}={owner}", *args[1:]])
    seen = False
    while process.poll() is None:
        try:
            inspected = subprocess.run(
                [docker, "inspect", "--format", "{{json .}}", name],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if inspected.returncode == 0:
                document = json.loads(inspected.stdout)
                if document.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == owner:
                    if not seen:
                        _append(
                            path,
                            {
                                "kind": "identity",
                                "container_id": document.get("Id"),
                                "image_id": document.get("Image"),
                                "name": name,
                                "cpu_limit": document.get("HostConfig", {}).get("NanoCpus"),
                                "memory_limit_bytes": document.get("HostConfig", {}).get("Memory"),
                            },
                        )
                        seen = True
                    stats = subprocess.run(
                        [docker, "stats", "--no-stream", "--format", "{{json .}}", name],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                    if stats.returncode == 0 and stats.stdout.strip():
                        _append(
                            path,
                            {
                                "kind": "usage",
                                "at_unix": time.time(),
                                "container_id": document.get("Id"),
                                "sample": json.loads(stats.stdout),
                            },
                        )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass  # Instrumentation failure is reported by missing identity/samples.
        time.sleep(0.4)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
