"""Explicitly registered evaluators; no executable imports from untrusted manifests."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent_infra.tasks.api import EvaluationPlan, TaskDefinition
from agent_infra.tasks.manifest import canonical, resolve_material
from agent_infra.tasks.service import verify_evaluation_inputs


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    status: str
    native_result_json: str | None = None
    error_code: str | None = None


Evaluator = Callable[[TaskDefinition, EvaluationPlan], str]


class EvaluatorRegistry:
    def __init__(self, evaluators: Mapping[str, Evaluator]) -> None:
        self._evaluators = dict(evaluators)

    def evaluate(self, task: TaskDefinition, plan: EvaluationPlan) -> EvaluationResult:
        evaluator = self._evaluators.get(plan.evaluator_ref)
        if evaluator is None:
            raise ValueError("evaluator is not registered; native evaluation is unavailable")
        verify_evaluation_inputs(task, plan)
        try:
            raw_result = evaluator(task, plan)
            canonical(json.loads(raw_result))
            verify_evaluation_inputs(task, plan)
        except Exception:
            # Private evaluator tracebacks/results must not leak to solver channels.
            return EvaluationResult("failed", error_code="evaluation_failed")
        return EvaluationResult("succeeded", native_result_json=raw_result)


def evaluate_text_example(task: TaskDefinition, plan: EvaluationPlan) -> str:
    """Exact-text platform fixture only; never substituted for a native benchmark scorer."""
    expected = next(item for item in task.materials if item.id == "expected")
    if "solver" in expected.audiences:
        raise ValueError("example answer must be private")
    expected_text = resolve_material(task.root, expected.source).read_text()
    result = resolve_material(plan.submission_root, "result.txt")
    passed = result.is_file() and result.read_text() == expected_text
    return '{"passed": true}' if passed else '{"passed": false}'
