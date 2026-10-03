#!/usr/bin/env python3
"""Verify step of the ResearchClawBench adapter: score one trial with the original judge.

Runs in the RCB `.venv` as an Orbit process run. Builds a workspace in $ORBIT_OUTPUT that links to
the files collected from the solve run, calls `evaluation.score.score_run` (which writes
`_score.json` there) and summarizes every attempt in $ORBIT_OUTPUT/result.json for the adapter.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_dotenv(path):
    """KEY=VALUE lines; variables already set (e.g. passed by Orbit) win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rcb", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--collected", required=True)
    p.add_argument("--mode", default="enhanced")
    p.add_argument("--model", default="")
    p.add_argument("--attempts", type=int, default=1)
    p.add_argument("--dotenv", action="store_true")
    a = p.parse_args()

    out = os.environ["ORBIT_OUTPUT"]
    if a.dotenv:
        load_dotenv(os.path.join(a.rcb, "evaluation", ".env"))
    sys.dont_write_bytecode = True
    sys.path.insert(0, a.rcb)
    from evaluation.score import score_run

    root = Path(out) / "workspaces"
    ws = root / a.run_id
    ws.mkdir(parents=True, exist_ok=True)
    for name in ("INSTRUCTIONS.md", "code", "outputs", "report"):
        src = os.path.join(a.collected, name)
        if os.path.exists(src) and not (ws / name).exists():
            os.symlink(src, ws / name)
    with open(ws / "_meta.json", "w", encoding="utf-8") as f:
        json.dump({"task_id": a.task, "run_id": a.run_id, "agent_name": a.agent}, f, indent=2)

    attempts = []
    for i in range(max(1, a.attempts)):
        r = score_run(a.run_id, scorer_model=a.model or None, workspace_root=root,
                      scoring_mode=a.mode)
        if "error" in r:
            attempts.append({"error": r["error"]})
            print(f"attempt {i + 1}: {r['error']}", flush=True)
            break
        failed = [it["index"] for it in r["items"] if it.get("raw_response_parsed") is None]
        attempts.append({
            "total": r["total_score"],
            "items": len(r["items"]),
            "failedItems": failed,
            "scorerModel": r.get("scorer_model"),
            "scoringMode": r.get("scoring_mode"),
        })
        print(f"attempt {i + 1}: total {r['total_score']} ({r.get('scorer_model')}, "
              f"{r.get('scoring_mode')}); {len(failed)}/{len(r['items'])} judge calls failed",
              flush=True)
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"attempts": attempts}, f, indent=2)


if __name__ == "__main__":
    main()
