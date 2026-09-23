"""Public, benchmark-neutral policy for a bounded outer optimization campaign."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_infra.benchmarks.api import Contract, Name, PositiveInt


class CampaignPolicy(Contract):
    schema_version: Literal[1] = 1
    campaign_id: Name
    max_trials: PositiveInt
    max_wall_seconds: PositiveInt
    allowed_parameter_keys: tuple[Name, ...] = ()
    allowed_candidate_fields: tuple[
        Literal["configuration_digest", "agent_version", "model"], ...
    ] = ()
    feedback_metrics: Annotated[tuple[Name, ...], Field(min_length=1)]
    selection_metric: Name
    direction: Literal["maximize", "minimize"]
    minimum_improvement: Annotated[float, Field(ge=0)] = 0

    @model_validator(mode="after")
    def valid_policy(self) -> Self:
        if len(set(self.allowed_parameter_keys)) != len(self.allowed_parameter_keys):
            raise ValueError("allowed parameter keys must be unique")
        if len(set(self.allowed_candidate_fields)) != len(self.allowed_candidate_fields):
            raise ValueError("allowed candidate fields must be unique")
        if len(set(self.feedback_metrics)) != len(self.feedback_metrics):
            raise ValueError("feedback metrics must be unique")
        if self.selection_metric not in self.feedback_metrics:
            raise ValueError("selection metric must be released feedback")
        if not self.allowed_parameter_keys and not self.allowed_candidate_fields:
            raise ValueError("campaign needs an explicit candidate modification scope")
        return self
