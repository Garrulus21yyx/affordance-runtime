from __future__ import annotations

import asyncio

import pytest

from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.evaluation_control import (
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.evaluation import (
    ActionEvaluation,
    CriterionEvaluation,
    TaskEvaluation,
    TaskEvaluationStatus,
)


def test_public_evaluation_statuses_require_enum_instances() -> None:
    with pytest.raises(TypeError, match="action evaluation status"):
        ActionEvaluation("request", "before", "after", "unknown", "reason")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="criterion evaluation status"):
        CriterionEvaluation("criterion", "unknown", (), "reason")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="task evaluation status"):
        TaskEvaluation("task", "observation", "complete", "reason")  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ("criteria", "outputs"))
def test_task_evaluation_children_require_typed_contracts(field: str) -> None:
    values = {field: (object(),)}
    with pytest.raises(TypeError, match=f"task evaluation {field}"):
        TaskEvaluation(
            "task", "observation", TaskEvaluationStatus.INCOMPLETE, "reason", **values,
        )


def test_evaluator_boundaries_reject_noncontract_results_before_projection() -> None:
    class MalformedEvaluator:
        async def evaluate(self, *_args):
            return object()

    malformed = MalformedEvaluator()
    with pytest.raises(ValueError, match="task evaluator returned a malformed result"):
        asyncio.run(validated_task_evaluation(malformed, object(), object()))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="action evaluator returned a malformed result"):
        asyncio.run(
            validated_action_evaluation(
                malformed, object(), object(), object(), object(), object(),  # type: ignore[arg-type]
            )
        )


def test_policy_and_model_failure_kinds_and_flags_are_typed() -> None:
    with pytest.raises(TypeError, match="policy failure kind"):
        PolicyFailure("timeout", "safe")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="policy failure retryable"):
        PolicyFailure(ModelFailureKind.TIMEOUT, "safe", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="model failure kind"):
        ModelFailure("timeout", "safe", False)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="model failure retryable"):
        ModelFailure(ModelFailureKind.TIMEOUT, "safe", 0)  # type: ignore[arg-type]
