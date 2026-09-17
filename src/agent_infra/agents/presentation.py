"""Provider output presentation; no storage paths or private diagnostics."""

from collections.abc import Mapping


def event_text(payload: Mapping[str, object]) -> str:
    native = payload.get("native")
    if not isinstance(native, dict):
        return ""
    texts: list[str] = []

    def visit(value: object, depth: int = 0) -> None:
        if depth > 5 or len(texts) >= 20:
            return
        if isinstance(value, dict):
            for key in ("text", "command", "name", "output", "aggregated_output", "result"):
                text = value.get(key)
                if isinstance(text, str):
                    texts.append(text[:4000])
            for key in ("item", "message", "content", "tool_calls", "function"):
                visit(value.get(key), depth + 1)
        elif isinstance(value, list):
            for item in value[:20]:
                visit(item, depth + 1)

    visit(native)
    return "\n".join(texts)[:8000]
