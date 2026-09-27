"""Synthetic browser fixture. No models, Docker or production state."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_infra.bootstrap.benchmark_console import BenchmarkConsole
from agent_infra.bootstrap.benchmark_workspace import BenchmarkWorkspace
from agent_infra.gateways.http.server import create_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from benchmark_workspace import make_batch  # noqa: E402


def main():
    with TemporaryDirectory(prefix="benchmark-web-browser-") as directory:
        root = Path(directory)
        first = make_batch(root / "baseline", "baseline")
        second = make_batch(root / "revised", "revised")
        third = make_batch(root / "incomplete", "partial", incomplete=True)
        state = root / "console"
        workspace = BenchmarkWorkspace(state)
        left = workspace.register({"path": str(first["root"])})["id"]
        right = workspace.register({"path": str(second["root"])})["id"]
        workspace.route("POST", ["settings"], {}, {"baseline": left})
        server = create_server(
            None,
            Path("src/web/dist"),
            "benchmark-browser-fixture-token-123456789",
            0,
            benchmark=BenchmarkConsole(state),
        )
        print(
            json.dumps(
                {
                    "port": server.server_port,
                    "left": left,
                    "right": right,
                    "run": second["runs"][0]["run_id"],
                    "third": str(third["root"]),
                }
            ),
            flush=True,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
