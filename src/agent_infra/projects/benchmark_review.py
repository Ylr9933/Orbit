"""Bounded authored research reviews; evidence and snapshot checks live in composition."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=4000)]


class EvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: Annotated[str, Field(min_length=1, max_length=120)]
    member: Annotated[str, Field(max_length=1000)] | None = None
    step: Annotated[int, Field(ge=0, le=100000)] | None = None


class ReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: Annotated[str, Field(min_length=1, max_length=100)]
    observation: Text
    interpretation: Text
    next: Text
    evidence: Annotated[list[EvidenceLink], Field(min_length=1, max_length=20)]


class ResearchReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    snapshot: Annotated[str, Field(min_length=64, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    author: Annotated[str, Field(min_length=1, max_length=120)]
    summary: Text
    report: Annotated[str, Field(min_length=1, max_length=30000)]
    cases: Annotated[list[ReviewCase], Field(max_length=100)]
    revision: Annotated[int, Field(ge=0)] = 0
