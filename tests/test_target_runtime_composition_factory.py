from __future__ import annotations

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TargetRuntime,
    TargetRuntimeStartOutcome,
)
from affordance_runtime.agent import TOOL_ACTION_DECISION_CAPABILITIES, compose_target_runtime


class _Policy:
    supported_decisions = TOOL_ACTION_DECISION_CAPABILITIES

    async def decide(self, context):
        del context
        raise AssertionError("composition test must not call policy")


class _Evaluator:
    async def evaluate(self, *args, **kwargs):
        del args, kwargs
        raise AssertionError("composition test must not call evaluators")


def test_public_target_composition_factory_builds_the_runtime_contract() -> None:
    evaluator = _Evaluator()

    runtime = compose_target_runtime(
        _Policy(),
        evaluator,
        evaluator,
        required_decisions=TOOL_ACTION_DECISION_CAPABILITIES,
    )

    assert isinstance(runtime, TargetRuntime)
    assert runtime.required_decisions == TOOL_ACTION_DECISION_CAPABILITIES
    assert runtime.decision_ports.local_objective_proposer is None


def test_root_package_exports_target_natural_language_start_contracts() -> None:
    assert NaturalLanguageTaskRequest.__name__ == "NaturalLanguageTaskRequest"
    assert TargetRuntimeStartOutcome.__name__ == "TargetRuntimeStartOutcome"
