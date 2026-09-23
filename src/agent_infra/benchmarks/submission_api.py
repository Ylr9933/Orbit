"""Optional adapter-owned native submission extension; no universal leaderboard API."""

from typing import Literal, Protocol

from agent_infra.benchmarks.api import AdapterIdentity, Contract, Digest, ExecutionPlan, Name
from agent_infra.records.api import ArtifactRef, RecordsReader


class NativeSubmissionPlan(Contract):
    target: Name
    format: Name
    instructions: tuple[Name, ...] = ()
    supports_send: bool = False


class SubmissionHandoff(Contract):
    schema_version: Literal[1] = 1
    operation_id: Name
    run_id: Name
    attempt_id: Name
    candidate_id: Name
    adapter: AdapterIdentity
    suite_digest: Digest
    runner_digest: Digest
    artifact_id: Name
    artifact_digest: Digest
    plan: NativeSubmissionPlan


class NativeSubmissionReceipt(Contract):
    status: Literal["submitted", "rejected"]
    native_submission_id: Name | None = None
    evidence_reference: Name | None = None


class NativeSubmissionAdapter(Protocol):
    """Trusted native package owns format and remote protocol, not core Run logic."""

    def prepare_submission(
        self, plan: ExecutionPlan, artifact: ArtifactRef, native_result: dict[str, object]
    ) -> NativeSubmissionPlan: ...

    def send_submission(
        self, handoff: SubmissionHandoff, artifact: ArtifactRef, records: RecordsReader
    ) -> NativeSubmissionReceipt: ...
