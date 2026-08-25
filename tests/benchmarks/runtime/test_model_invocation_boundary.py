from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_counting_decision_port_counts_only_transport_attempts() -> None:
    class WrappedPort:
        async def generate(self, request):
            del request
            return ModelInvocationResult(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "role repair failed", False),
                attempts=(
                    ModelGenerationAttempt(1, "initial", "grounded_tools.v2", "failed"),
                    ModelGenerationAttempt(2, "initial_provider_retry", "grounded_tools.v2", "accepted"),
                ),
                diagnostics={
                    "policy_model_call_count": 2,
                    "provider_retry_count": 1,
                },
            )

    instrumentation = BenchmarkInstrumentation()
    outcome = asyncio.run(CountingDecisionPort(WrappedPort(), instrumentation).generate(object()))

    assert isinstance(outcome, ModelInvocationResult)
    assert [item.phase for item in outcome.attempts] == [
        "initial",
        "initial_provider_retry",
    ]
    assert instrumentation.provider_attempts == 2
    assert instrumentation.provider_retry_count == 1
    assert instrumentation.action_policy_ordinary_calls == 1
    assert instrumentation.action_policy_recovery_calls == 0
    assert instrumentation.representation_repair_calls == 0


def test_counting_decision_port_separates_recovery_and_representation_repair() -> None:
    class WrappedPort:
        async def generate(self, request):
            del request
            return ModelInvocationResult(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "repair failed", False),
                attempts=(
                    ModelGenerationAttempt(1, "deliberate", "grounded_tools.v2", "invalid"),
                    ModelGenerationAttempt(
                        2,
                        "representation_repair",
                        "grounded_tools.v2",
                        "failed",
                    ),
                ),
                diagnostics={"policy_model_call_count": 2},
            )

    instrumentation = BenchmarkInstrumentation()
    request = SimpleNamespace(agent_context=SimpleNamespace(control_feedback={"kind": "effect_stall"}))

    asyncio.run(CountingDecisionPort(WrappedPort(), instrumentation).generate(request))

    assert instrumentation.action_policy_ordinary_calls == 0
    assert instrumentation.action_policy_recovery_calls == 1
    assert instrumentation.representation_repair_calls == 1
    assert instrumentation.provider_attempts == 2


def test_counting_decision_port_reports_serialized_multiple_call_attempt() -> None:
    class WrappedPort:
        async def generate(self, request):
            del request
            return ModelInvocationResult(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "fixture", False),
                attempts=(
                    ModelGenerationAttempt(1, "ordinary", "grounded_tools.v2", "accepted"),
                ),
                diagnostics={
                    "policy_model_call_count": 1,
                    "tool_resolution_code": "accepted",
                    "multiple_tool_call_attempt_count": 1,
                    "discarded_protocol_call_count": 1,
                },
            )

    instrumentation = BenchmarkInstrumentation()

    asyncio.run(CountingDecisionPort(WrappedPort(), instrumentation).generate(object()))

    assert instrumentation.multiple_tool_call_count == 1
    assert instrumentation.valid_tool_call_count == 1
    assert instrumentation.provider_attempts == 1


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
