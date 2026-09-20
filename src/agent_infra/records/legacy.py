"""Legacy events.jsonl/result.json writer; retained for existing direct callers."""

import json
from pathlib import Path
from typing import Any

from agent_infra.records._serialization import _now


class LocalRunJournal:
    """Compatibility writer for legacy callers; new Run code uses LocalRecordsStore."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def event(self, kind: str, **fields: Any) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": _now().isoformat(), "kind": kind, **fields}) + "\n")

    def finish(self, result: dict[str, Any]) -> None:
        temporary = self.root / "result.tmp"
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.replace(self.root / "result.json")
