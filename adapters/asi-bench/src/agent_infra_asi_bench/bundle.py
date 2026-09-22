"""Build a local native seed42 bundle without authentication or upload."""

import argparse
import json
from pathlib import Path

from ai4sci_bench.submission.bundle import build_submission


def build_local_bundle(results_dir: Path, output_dir: Path) -> dict:
    destination = output_dir.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = build_submission(
        results_dir.resolve(),
        output_path=destination,
        archive=False,
        benchmark_repo="Apexintelligence-AI/ASI-Bench-seed42",
    )
    return {
        "bundle": str(result.bundle_dir.resolve()),
        "instance_count": result.instance_count,
        "uploaded": False,
        "authenticated": False,
        "official_score": None,
        "evaluation": "external_after_submission",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_local_bundle(args.results_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
