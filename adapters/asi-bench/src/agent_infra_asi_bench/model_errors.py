"""Recognize terminal provider errors without exporting credential-bearing messages."""

import json


def model_failure(output: dict) -> str | None:
    raw = output.get("error_message")
    if not isinstance(raw, str):
        return None
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(event, dict) or event.get("type") not in {"error", "turn.failed"}:
            continue
        detail = event.get("error") or {}
        message = event.get("message") or (
            detail.get("message") if isinstance(detail, dict) else ""
        )
        text = str(message).lower()
        if "model" in text and any(
            value in text
            for value in (
                "not supported",
                "does not exist",
                "do not have access",
                "model_not_found",
            )
        ):
            return "model_unavailable"
        if any(
            value in text for value in ("invalid_api_key", "authentication_error", "unauthorized")
        ):
            return "model_authentication_failed"
    return None
