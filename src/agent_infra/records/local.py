"""Controller-only local journal. No claim of durable distributed state recovery."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LocalRunJournal:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def event(self, kind: str, **fields: Any) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"at": datetime.now(UTC).isoformat(), "kind": kind, **fields}) + "\n"
            )

    def finish(self, result: dict[str, Any]) -> None:
        temporary = self.root / "result.tmp"
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.replace(self.root / "result.json")
