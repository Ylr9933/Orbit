"""Standalone container client for the scoped Planner mailbox (standard library only).

Copied read-only into /inputs. No controller address, token or Docker access is present.
"""

import argparse
import json
import os
import time
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Project/workflow-bound research actions")
    parser.add_argument("action", choices=("context", "status", "step", "read", "analysis"))
    parser.add_argument(
        "--json", default="{}", help="JSON options; stable operation_id for mutations"
    )
    args = parser.parse_args()
    key = uuid.uuid4().hex
    root = Path("/workspace")
    request = {"id": key, "action": args.action, "options": json.loads(args.json)}
    temp = root / (key + ".tmp")
    temp.write_text(json.dumps(request))
    os.replace(temp, root / "request.json")
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        try:
            response = json.loads((root / "response.json").read_text())
            if response["id"] == key:
                print(json.dumps(response, ensure_ascii=False))
                if "error" in response:
                    raise SystemExit(1)
                return
        except (FileNotFoundError, ValueError):
            pass
        time.sleep(0.1)
    raise SystemExit(
        "Planner bridge timeout; inspect workflow status before retrying the same operation"
    )


if __name__ == "__main__":
    main()
