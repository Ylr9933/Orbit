"""Fail early when contributor tooling differs from the supported baseline."""

import json
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "package.json").read_text())
    expected = {
        "node": "v" + (root / ".node-version").read_text().strip(),
        "pnpm": manifest["packageManager"].split("@")[1],
        "uv": "uv 0.12.10",
    }
    for tool, wanted in expected.items():
        try:
            actual = subprocess.check_output([tool, "--version"], text=True).strip()
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise SystemExit(f"{tool} unavailable; follow CONTRIBUTING.md") from error
        if actual != wanted and not (tool == "uv" and actual.startswith(wanted + " ")):
            raise SystemExit(f"{tool}: expected {wanted}, found {actual}")
        print(f"{tool}: {actual}")


if __name__ == "__main__":
    main()
