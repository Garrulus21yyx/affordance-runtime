from __future__ import annotations

import asyncio

import pytest

from affordance_runtime.agent import Abort
from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingDecisionPort,
)
from affordance_runtime.model.policy import (
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)


def test_model_invocation_result_requires_one_output_or_typed_failure() -> None:
    failure = ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False)

    with pytest.raises(ValueError, match="exactly one"):
        ModelInvocationResult()
    with pytest.raises(ValueError, match="exactly one"):
        ModelInvocationResult(output=object(), failure=failure)

    assert ModelInvocationResult(failure=failure).failure is failure


def test_counting_decision_port_uses_invocation_attempts_without_repair_double_count() -> None:
    class WrappedPort:
        last_schema_repair_count = 1
        last_model_call_count = 3
        last_provider_retry_count = 1
        last_generation_attempts = (
            ModelGenerationAttempt(1, "stale-mirror", "grounded_tools.v2", "accepted"),
        )

        async def generate(self, request):
            del request
            return ModelInvocationResult(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "role repair failed", False),
                attempts=(
                    ModelGenerationAttempt(1, "initial", "grounded_tools.v2", "failed"),
                    ModelGenerationAttempt(2, "initial_provider_retry", "grounded_tools.v2", "accepted"),
                    ModelGenerationAttempt(3, "tool_call_repair", "grounded_tools.v2", "schema_error"),
                ),
                repair_diagnostics=(
                    {"kind": "transport_retry", "phase": "initial_provider_retry"},
                    {"kind": "tool_call_repair", "phase": "tool_call_repair"},
                ),
            )

    instrumentation = BenchmarkInstrumentation()
    outcome = asyncio.run(CountingDecisionPort(WrappedPort(), instrumentation).generate(object()))

    assert isinstance(outcome, ModelInvocationResult)
    assert [item.phase for item in outcome.attempts] == [
        "initial",
        "initial_provider_retry",
        "tool_call_repair",
    ]
    assert instrumentation.provider_attempts == 3
    assert instrumentation.provider_retry_count == 1
    assert instrumentation.policy_schema_repair_count == 1


def test_invocation_attempts_are_role_output_lineage_not_runtime_authority() -> None:
    decision = ResolvedModelDecision(
        Abort("context:lineage", "done", "policy"),
        ModelMetadata(provider_id="fixture", model_id="scripted"),
    )
    result = ModelInvocationResult(
        output=decision,
        metadata=decision.metadata,
        attempts=(ModelGenerationAttempt(1, "initial", "grounded_tools.v2", "accepted"),),
        lineage={"role": "ActionPolicy"},
    )

    assert result.accepted
    assert result.decision is decision.decision
    assert "binding" not in result.lineage
    assert "dispatch" not in result.lineage
