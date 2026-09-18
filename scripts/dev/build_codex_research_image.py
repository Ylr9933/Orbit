"""Build a fixed CPU image from an installed official native Codex package, offline.

The Python base image must already exist locally. Nothing under CODEX_HOME is read.
This is explicit image preparation, never an automatic fallback during submission.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir", type=Path, help="Native vendor target directory containing bin/codex"
    )
    parser.add_argument("--tag", default="agent-infra/codex-research:0.154.0")
    parser.add_argument("--version", default="0.154.0")
    parser.add_argument("--base", default="python:3.12-slim")
    args = parser.parse_args()
    package = args.package_dir
    if package is None:
        executable = shutil.which("codex")
        if not executable:
            parser.error("install Codex first, or provide --package-dir")
        root = Path(executable).resolve().parent.parent
        candidates = list(root.glob("node_modules/@openai/codex-*/vendor/*/bin/codex"))
        if len(candidates) != 1:
            parser.error("cannot identify one native package; provide --package-dir")
        package = candidates[0].parent.parent
    binary = package / "bin/codex"
    version = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if version != "codex-cli " + args.version:
        parser.error(f"expected Codex {args.version}; found {version}")
    base_info = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", args.base], capture_output=True, text=True, check=True
        ).stdout
    )[0]
    base = base_info["Id"]
    base_reference = next(iter(base_info.get("RepoDigests") or ()), args.base)
    dockerfile = Path(__file__).resolve().parents[2] / "deploy/docker/codex-research.Dockerfile"
    with tempfile.TemporaryDirectory(prefix="agent-infra-codex-build-") as temporary:
        context = Path(temporary)
        shutil.copytree(package, context / "codex-package", symlinks=False)
        shutil.copyfile(dockerfile, context / "Dockerfile")
        subprocess.run(
            [
                "docker",
                "build",
                "--pull=false",
                "--network=none",
                "--tag",
                args.tag,
                "--build-arg",
                "PYTHON_IMAGE=" + base_reference,
                "--build-arg",
                "CODEX_VERSION=" + args.version,
                str(context),
            ],
            check=True,
        )
    with binary.open("rb") as file:
        binary_digest = hashlib.file_digest(file, "sha256").hexdigest()
    print(
        json.dumps(
            {
                "image": args.tag,
                "codex_version": args.version,
                "binary_sha256": binary_digest,
                "base_image_id": base,
            }
        )
    )


if __name__ == "__main__":
    main()
