"""Conservative diagnostics of archived ASI evidence, independent of numeric scores."""

import json
from typing import Any

SCORE_MEMBER = "outputs/benchflow_score.json"
TERMINAL_MEMBER = "outputs/evidence/codex-stdout.jsonl"


def evaluation_health(score: object) -> dict[str, Any]:
    unknown = {"status": "unknown", "issues": [], "member": SCORE_MEMBER}
    if not isinstance(score, dict) or score.get("schema_version") != 2:
        return unknown
    if not all(isinstance(score.get(k), list) for k in ("gate_results", "score_details")):
        return unknown
    issues: list[dict[str, str]] = []
    remaining = 20000

    def walk(value: object, path: str, depth: int = 0) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 64:
            raise ValueError("score diagnostic traversal limit")
        if isinstance(value, dict):
            if value.get("evaluator_unavailable") is True:
                issues.append({"kind": "judge_unavailable", "path": path})
            for key, item in value.items():
                if key in {"error", "setup_error", "message"} and isinstance(item, str):
                    if "FileNotFoundError" in item or "No such file or directory" in item:
                        issues.append({"kind": "missing_dependency", "path": f"{path}.{key}"})
                if isinstance(item, (dict, list)):
                    walk(item, f"{path}.{key}", depth + 1)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", depth + 1)

    try:
        for section in ("gate_results", "score_details"):
            walk(score[section], section)
    except ValueError:
        return unknown
    return {
        "status": "needs_review" if issues else "no_anomaly_detected",
        "issues": issues[:100],
        "issue_count": len(issues),
        "member": SCORE_MEMBER,
        "hard_gates_passed": score.get("hard_gates_passed"),
    }


def terminal_health(stdout: bytes | None, native_status: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unknown",
        "native_status": native_status,
        "member": TERMINAL_MEMBER,
        "status_conflict": False,
    }
    if stdout is None:
        return result
    terminal = None
    try:
        for line in stdout.decode("utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                return result
            if event.get("type") == "turn.started":
                terminal = None
            elif event.get("type") in {"turn.completed", "turn.failed"}:
                terminal = event
    except (ValueError, UnicodeError):
        return result
    if terminal is None:
        return result
    status = "completed" if terminal["type"] == "turn.completed" else "failed"
    if status == "failed" and "usage limit" in json.dumps(terminal).lower():
        status = "quota_exhausted"
    return {
        **result,
        "status": status,
        "status_conflict": native_status is not None
        and (
            (status == "completed" and native_status != "completed")
            or (status != "completed" and native_status in {"completed", "timeout"})
        ),
    }
