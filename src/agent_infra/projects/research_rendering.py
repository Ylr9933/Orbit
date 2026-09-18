"""Readable projections of a research snapshot, not additional sources of truth."""

from typing import Any

from agent_infra.projects.api import Project
from agent_infra.projects.research_api import ResearchDraft


def _bullets(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items) or "Not specified."


def render_research(project: Project, draft: ResearchDraft, revision: int) -> dict[str, str]:
    doc = draft.to_dict()
    brief, plan = doc["brief"], doc["plan"]
    header = (
        f"<!-- agent-infra project={project.project_id} research_revision={revision} "
        f"digest={draft.digest} -->\n\n"
    )
    claims = "\n".join(
        f"- [{item['origin']}] {item['text']}"
        + (" (" + ", ".join(item["references"]) + ")" if item["references"] else "")
        for item in doc["claims"]
    )
    goal = (
        f"# Research goal\n\n## Original user request\n\n{project.original_goal}\n\n"
        f"## Current question\n\n{brief['question'] or 'Pending discussion.'}\n\n"
        f"## Constraints\n\n{_bullets(brief['constraints'])}\n\n"
        f"## Success criteria\n\n{brief['success_criteria'] or 'Not specified.'}\n\n"
        f"## Open questions\n\n{_bullets(brief['unknowns'])}\n"
    )
    background = (
        f"# Research background\n\n{brief['background'] or 'Not researched yet.'}\n\n"
        f"## Important claims and their declared origins\n\n{claims or 'None recorded.'}\n\n"
        "Origins and references are declarations, not automatic fact checking.\n"
    )
    parts = ["# Research plan", plan["summary"] or "No plan recorded."]
    for experiment in plan["experiments"]:
        parts.append(f"## {experiment['id']}: {experiment['title'] or 'Untitled experiment'}")
        for key in ("hypothesis", "method", "controls", "variables", "stopping_condition"):
            parts.append(
                f"### {key.replace('_', ' ').capitalize()}\n\n{experiment[key] or 'Not specified.'}"
            )
        parts.append(
            "### Inputs\n\n"
            + _bullets(
                [
                    f"{item['path']} — {item['description']} "
                    f"(version: {item['version'] or 'unknown'})"
                    for item in experiment["inputs"]
                ]
            )
        )
        parts.append(
            "### Metrics\n\n"
            + _bullets([f"{item['name']} ({item['direction']})" for item in experiment["metrics"]])
        )
        parts.append("### Outputs\n\n" + _bullets(experiment["outputs"]))
        parts.append(
            "### Resource request\n\n" + (experiment["resource_request"] or "Not specified.")
        )
    parts.append(
        "## Next step\n\n" + (doc["next_step"] or "Clarify the next useful step with the user.")
    )
    return {
        "docs/research-goal.md": header + goal,
        "docs/background.md": header + background,
        "docs/research-plan.md": header + "\n\n".join(parts) + "\n",
    }
