"""Pinned, evidence-backed compatibility claims; never infer official certification."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_infra.benchmarks.api import Contract, Digest, Name


class CompatibilityEntry(Contract):
    alias: Name
    adapter_id: Name
    distribution: Name
    adapter_version: Name
    suite_digest: Digest
    runner_digest: Digest
    profile: Name
    backend: Name
    agent: Name
    agent_version: Name
    model: Name
    level: Literal["indexed", "runnable", "scored", "protocol_validated"]
    evidence: tuple[Name, ...] = ()
    official_submission: Literal["unsupported", "manual", "native"] = "unsupported"
    limitations: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def evidence_required(self) -> Self:
        if self.level != "indexed" and not self.evidence:
            raise ValueError("runnable/scored/validated claims require evidence references")
        if self.official_submission != "unsupported" and not self.evidence:
            raise ValueError("submission capability requires evidence references")
        return self


class CompatibilityMatrix(Contract):
    schema_version: Literal[1] = 1
    entries: tuple[CompatibilityEntry, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def unique_tuples(self) -> Self:
        identities = [
            (
                item.adapter_id,
                item.alias,
                item.adapter_version,
                item.suite_digest,
                item.runner_digest,
                item.profile,
                item.backend,
                item.agent,
                item.agent_version,
                item.model,
            )
            for item in self.entries
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate exact compatibility tuple")
        return self


def read_matrix(path: Path) -> CompatibilityMatrix:
    return CompatibilityMatrix.model_validate_json(path.read_bytes())
