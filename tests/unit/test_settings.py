"""Configuration precedence and failure behavior, independent of runtime services."""

from pathlib import Path

import pytest

from agent_infra.bootstrap.settings import load_settings


def test_file_and_environment_precedence_without_creating_state(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('state_dir = "./unused"\nlog_level = "DEBUG"\n')
    state = tmp_path / "state"
    result = load_settings(config, {"AGENT_INFRA_STATE_DIR": str(state)})
    assert result.state_dir == state
    assert result.log_level == "DEBUG"
    assert not state.exists()


@pytest.mark.parametrize(
    "content",
    ['log_level = "TRACE"', "state_dir = 3", 'state_dir = ""', "typo = true", "broken = ["],
)
def test_rejects_invalid_configuration(tmp_path: Path, content: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(content)
    with pytest.raises(ValueError):
        load_settings(config, {})


def test_missing_explicit_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.toml", {})


def test_invalid_environment_is_not_silently_ignored() -> None:
    with pytest.raises(ValueError, match="log_level"):
        load_settings(environ={"AGENT_INFRA_LOG_LEVEL": "INVALID"})
