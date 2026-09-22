"""Deterministic no-model producer used only by the engineering profile."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    (root / "results").mkdir(exist_ok=True)
    (root / "analysis.py").write_text(
        "from pathlib import Path\n"
        "Path('results').mkdir(exist_ok=True)\n"
        "print('BM02-B deterministic fixture')\n",
        encoding="utf-8",
    )
    (root / "results" / "solutions.csv").write_text("instance_id,u,v,status\n", encoding="utf-8")
    (root / "results" / "instance_summary.csv").write_text("instance_id,status\n", encoding="utf-8")
    (root / "_trajectory.jsonl").write_text(
        json.dumps({"type": "fixture", "message": "created deterministic outputs"}) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
