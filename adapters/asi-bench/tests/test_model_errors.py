import json

import pytest
from agent_infra_asi_bench.model_errors import model_failure


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "The 'gpt-6-sol' model is not supported when using Codex with a ChatGPT account.",
            "model_unavailable",
        ),
        ("invalid_api_key", "model_authentication_failed"),
        ("experiment failed: unsupported matrix shape", None),
    ],
)
def test_terminal_provider_errors_are_classified(message, expected):
    payload = {"error_message": json.dumps({"type": "turn.failed", "error": {"message": message}})}
    assert model_failure(payload) == expected


def test_metadata_warning_is_not_runtime_failure():
    payload = {
        "error_message": json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "error", "message": "Model metadata for gpt-6-sol not found"},
            }
        )
    }
    assert model_failure(payload) is None
    assert model_failure({}) is None
