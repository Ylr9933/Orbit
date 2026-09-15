"""Task definitions, deterministic loading and preparation services."""

from agent_infra.tasks.api import AgentTaskView, TaskDefinition, TaskSnapshot
from agent_infra.tasks.authoring import apply_research_proposal
from agent_infra.tasks.manifest import freeze_task, load_task, validate_task
from agent_infra.tasks.service import (
    build_agent_view,
    build_evaluation_plan,
    create_research_draft,
    materialize_agent_view,
    review_draft,
    validate_resource_plan,
    verify_evaluation_inputs,
    write_manifest,
)

__all__ = [
    "apply_research_proposal",
    "AgentTaskView",
    "TaskDefinition",
    "TaskSnapshot",
    "build_agent_view",
    "build_evaluation_plan",
    "create_research_draft",
    "freeze_task",
    "load_task",
    "materialize_agent_view",
    "review_draft",
    "validate_resource_plan",
    "validate_task",
    "verify_evaluation_inputs",
    "write_manifest",
]
