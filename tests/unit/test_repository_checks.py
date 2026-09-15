"""Ensure collaboration checks detect broken navigation and diverging rules."""

import runpy
from pathlib import Path

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/ci/check_repository.py"))[
    "check"
]


def test_policy_drift_and_missing_links_are_reported(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("canonical")
    (tmp_path / "CLAUDE.md").write_text("different")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text("[missing](missing.md)\n")
    problems = CHECK(tmp_path)
    assert len(problems) == 2
    assert any("differ" in problem for problem in problems)
    assert any("missing.md" in problem for problem in problems)


def test_external_links_and_fenced_examples_are_not_local_targets(tmp_path: Path) -> None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        (tmp_path / name).write_text("same")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text(
        "[rules](../AGENTS.md)\n[web](https://example.com)\n"
        "```markdown\n[example](not-a-file.md)\n```\n"
    )
    assert CHECK(tmp_path) == []
