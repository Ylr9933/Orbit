import pytest
from agent_infra_asi_bench.native_cli import configure_codex_version
from ai4sci_bench.runner.task_image import AGENT_INSTALL_COMMANDS, TaskImageBuilder


def test_version_pin_changes_native_image_cache_without_changing_other_agents(tmp_path):
    original = dict(AGENT_INSTALL_COMMANDS)
    try:
        builder = TaskImageBuilder(tmp_path)
        metadata = {"id": "task", "_runtime_packages": []}
        before = builder._task_agent_image_tag(metadata, "codex")
        configure_codex_version("0.157.1")
        after = builder._task_agent_image_tag(metadata, "codex")
        assert before != after
        assert AGENT_INSTALL_COMMANDS["codex"] == ["npm install -g @openai/codex@0.157.1"]
        assert {k: v for k, v in AGENT_INSTALL_COMMANDS.items() if k != "codex"} == {
            k: v for k, v in original.items() if k != "codex"
        }
    finally:
        AGENT_INSTALL_COMMANDS.clear()
        AGENT_INSTALL_COMMANDS.update(original)


@pytest.mark.parametrize("version", ["latest", "0.157", "0.157.1;echo bad"])
def test_unpinned_or_executable_version_is_rejected(version):
    with pytest.raises(ValueError, match="exact release"):
        configure_codex_version(version)
