"""Pin the CLI installation input, then delegate execution to the native ASI CLI.

The pinned ASI builder includes install commands in its image cache key. Changing
this input builds a separate image without editing task/scorer files or retagging
shared images. This is deliberately specific to the pinned upstream revision.
"""

import re
import runpy
import sys


def configure_codex_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Codex version must be an exact release (major.minor.patch)")
    from ai4sci_bench.runner.task_image import AGENT_INSTALL_COMMANDS

    AGENT_INSTALL_COMMANDS["codex"] = [f"npm install -g @openai/codex@{version}"]


def main() -> None:
    configure_codex_version(sys.argv[1])
    sys.argv = ["ai4sci_bench.cli", *sys.argv[2:]]
    runpy.run_module("ai4sci_bench.cli", run_name="__main__")


if __name__ == "__main__":
    main()
