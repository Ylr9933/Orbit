"""Task definitions, deterministic loading and preparation services."""

from agent_infra.tasks.api import AgentTaskView, TaskDefinition, TaskReference, TaskSnapshot
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
from agent_infra.tasks.settings import load_execution_settings

__all__ = [
    "apply_research_proposal",
    "AgentTaskView",
    "TaskDefinition",
    "TaskReference",
    "TaskSnapshot",
    "build_agent_view",
    "build_evaluation_plan",
    "create_research_draft",
    "freeze_task",
    "load_task",
    "load_execution_settings",
    "materialize_agent_view",
    "review_draft",
    "validate_resource_plan",
    "validate_task",
    "verify_evaluation_inputs",
    "write_manifest",
]
