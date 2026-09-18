"""Packaged, provider-neutral research workflow, installable as a local Codex skill."""

from importlib.resources import files
from pathlib import Path

from agent_infra.projects import _filesystem as fs
from agent_infra.projects.api import Project


def research_skill() -> dict[str, str]:
    root = files("agent_infra.projects").joinpath("skills/agent-infra-research")
    return {
        name: root.joinpath(name).read_text("utf-8")
        for name in ("SKILL.md", "references/commands.md")
    }


def install_research_skill(project: Project) -> str:
    contents = research_skill()
    with (
        fs.directory(Path(project.workspace)) as root,
        fs.child_directory(root, ".agents", create=True) as agents,
        fs.child_directory(agents, "skills", create=True) as parent,
    ):
        name = "agent-infra-research"
        if fs.exists(parent, name):
            with fs.child_directory(parent, name) as child:
                fs.verify(child, contents, ("references",))
        else:
            stage = ".research-skill-" + project.project_id
            with fs.child_directory(parent, stage, create=True) as child:
                fs.populate(child, contents, ("references",))
            fs.publish(parent, stage, name)
    return str(Path(project.workspace) / ".agents/skills" / name)
