"""Optional SDK execution extension 1.0; planning-only packages remain valid."""

from typing import Protocol

from agent_infra.benchmarks.api import Contract, ExecutionPlan
from agent_infra.environments.api import ProcessCommand


class NativeInvocation(Contract):
    command: ProcessCommand
    outputs: tuple[str, ...] = ()


class BenchmarkExecutionAdapter(Protocol):
    """Pure translation. Do not execute anything in this method."""

    def invocation(self, plan: ExecutionPlan) -> NativeInvocation: ...
