"""Provider registry behavior."""

import pytest

from agent_infra.agents import AgentRegistry
from agent_infra.agents.claude_code import ClaudeCodeAdapter
from agent_infra.agents.codex import CodexAdapter
from agent_infra.agents.deepseek_harness import DeepSeekHarnessAdapter


def test_registry_selects_canonical_provider_and_alias() -> None:
    registry = AgentRegistry(
        (CodexAdapter(), ClaudeCodeAdapter(), DeepSeekHarnessAdapter()),
        aliases={"claude": "claude-code", "deepseek-harness": "dsh"},
    )

    assert registry.providers == ("claude-code", "codex", "dsh")
    assert registry.get("claude").descriptor.provider == "claude-code"
    assert registry.get("deepseek-harness").descriptor.provider == "dsh"


def test_registry_rejects_unknown_provider() -> None:
    registry = AgentRegistry((CodexAdapter(),))

    with pytest.raises(ValueError, match="choose one of: codex"):
        registry.get("unknown")
