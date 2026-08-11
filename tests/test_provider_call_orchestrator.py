from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from affordance_runtime.model_boundary.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderFailureCode,
)
from affordance_runtime.model_policy.contracts import (
    ModelDecisionRequest,
    ModelDecisionResponse,
    ModelMetadata,
)
from affordance_runtime.model_policy.provider_orchestrator import (
    ProviderAttemptStatus,
    ProviderCallOrchestrator,
    ProviderCallPolicy,
)


def _request() -> ModelDecisionRequest:
    return ModelDecisionRequest("model-request:test", "{}", "v1", "decide", {})


def _response(response_id: str = "response:1") -> ModelDecisionResponse:
    return ModelDecisionResponse(
        '{"decision":"ok"}',
        ModelMetadata(response_id=response_id),
    )


@dataclass
class _Port:
    outcomes: list[ModelDecisionResponse | ModelFailure]
    provider_id: str = "provider"
    model_id: str = "model"
    compatibility_key: str = "schema:grounding"
    calls: int = field(default=0, init=False)

    async def generate(self, request):
        self.calls += 1
        return self.outcomes.pop(0)


def test_retryable_rate_limit_retries_without_creating_a_new_request() -> None:
    port = _Port([
        ModelFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            "rate limited",
            True,
            ProviderFailureCode.RATE_LIMITED,
            0.0,
        ),
        _response(),
    ])
    orchestrator = ProviderCallOrchestrator(
        (port,),
        ProviderCallPolicy(3, (0.0, 0.0), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelDecisionResponse)
    assert port.calls == 2
    assert outcome.metadata.rate_limit_retry_count == 1
    assert outcome.metadata.transient_retry_count == 0
    assert [item.policy_request_id for item in orchestrator.last_attempts] == [
        "model-request:test",
        "model-request:test",
    ]
    assert [item.status for item in orchestrator.last_attempts] == [
        ProviderAttemptStatus.RETRYABLE_FAILURE,
        ProviderAttemptStatus.ACCEPTED,
    ]


def test_nonretryable_failure_fails_immediately_without_fallback() -> None:
    primary = _Port([
        ModelFailure(
            ModelFailureKind.REFUSED,
            "authentication failed",
            False,
            ProviderFailureCode.AUTHENTICATION,
        )
    ])
    fallback = _Port([_response()], provider_id="fallback")
    orchestrator = ProviderCallOrchestrator(
        (primary, fallback),
        ProviderCallPolicy(3, (0.0, 0.0), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind is ModelFailureKind.REFUSED
    assert primary.calls == 1 and fallback.calls == 0
    assert orchestrator.last_fallback_count == 0


def test_exhaustion_is_typed_and_fallback_is_compatible() -> None:
    def unavailable() -> ModelFailure:
        return ModelFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            "unavailable",
            True,
            ProviderFailureCode.UNAVAILABLE,
        )
    primary = _Port([unavailable(), unavailable()], provider_id="primary")
    fallback = _Port([unavailable(), unavailable()], provider_id="fallback")
    orchestrator = ProviderCallOrchestrator(
        (primary, fallback),
        ProviderCallPolicy(2, (0.0,), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind is ModelFailureKind.PROVIDER_EXHAUSTED
    assert outcome.retryable is False
    assert len(orchestrator.last_attempts) == 4
    assert orchestrator.last_fallback_count == 1


def test_fallback_rejects_a_different_schema_or_capability_profile() -> None:
    first = _Port([])
    second = _Port([], compatibility_key="different")
    with pytest.raises(ValueError, match="schema/capability"):
        ProviderCallOrchestrator((first, second))
