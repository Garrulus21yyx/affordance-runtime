"""Model-backed post-observation LocalObjective proposal port."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field

from affordance_runtime.agent.local_objective_proposal import (
    LocalObjectiveProposalOutcome,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.contracts import (
    ModelDecisionRequest,
    ModelMetadata,
    ResolvedLocalObjectiveOutcome,
)
from affordance_runtime.model_policy.objective_spec import (
    OBJECTIVE_SCHEMA_VERSION,
    local_objective_response_schema,
)
from affordance_runtime.model_policy.port import StructuredObjectiveModelPort
from affordance_runtime.model_policy.serialization import serialize_agent_context

_OBJECTIVE_INSTRUCTIONS = """
Resolve the explicitly enabled LocalObjective phase from current post-observation context.
Return one bounded proposal, not_required, needs_input, or unsupported outcome.
Use semantic selectors only; never emit E-refs, action IDs, DOM IDs, bindings,
private selectors, screen points, or coordinates. The proposal is not authority:
Runtime independently admits it and owns evidence, actions, effects, and completion.
""".strip()

_PUBLIC_FAILURES = {
    ModelFailureKind.PROVIDER_UNAVAILABLE: "objective proposal provider is unavailable",
    ModelFailureKind.PROVIDER_EXHAUSTED: "objective proposal providers exhausted bounded recovery",
    ModelFailureKind.TIMEOUT: "objective proposal provider timed out",
    ModelFailureKind.INVALID_RESPONSE: "objective proposal response was invalid",
    ModelFailureKind.SCHEMA_ERROR: "objective proposal violated the required schema",
    ModelFailureKind.REFUSED: "objective proposal provider refused the request",
    ModelFailureKind.INTERNAL_ERROR: "objective proposal could not be produced",
}


@dataclass(frozen=True)
class ModelBackedLocalObjectiveProposer:
    port: StructuredObjectiveModelPort
    call_timeout_s: float = 90.0
    last_metadata: ModelMetadata | None = field(default=None, init=False, compare=False)
    last_provider_attempts: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_fallback_count: int = field(default=0, init=False, compare=False)

    def __post_init__(self) -> None:
        if not 0 < self.call_timeout_s <= 300:
            raise ValueError("objective proposal timeout must be in (0, 300]")
        transport_timeout = getattr(self.port, "transport_timeout_s", None)
        if transport_timeout is not None and transport_timeout >= self.call_timeout_s:
            raise ValueError("objective transport timeout must be below the proposal deadline")

    async def propose(self, context: AgentContext) -> LocalObjectiveProposalOutcome:
        object.__setattr__(self, "last_metadata", None)
        object.__setattr__(self, "last_provider_attempts", ())
        object.__setattr__(self, "last_fallback_count", 0)
        try:
            request = _build_request(
                context,
                include_serialized_context=bool(
                    getattr(self.port, "requires_serialized_context", True)
                ),
            )
            outcome = await asyncio.wait_for(
                self.port.generate(request),
                timeout=self.call_timeout_s,
            )
        except TimeoutError:
            return _failure(ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False))
        except Exception:
            return _failure(ModelFailure(ModelFailureKind.INTERNAL_ERROR, "proposal port failed", False))
        finally:
            object.__setattr__(self, "last_provider_attempts", tuple(getattr(self.port, "last_attempts", ())))
            object.__setattr__(self, "last_fallback_count", int(getattr(self.port, "last_fallback_count", 0)))
        if isinstance(outcome, ModelFailure):
            return _failure(outcome)
        if not isinstance(outcome, ResolvedLocalObjectiveOutcome):
            return _failure(ModelFailure(ModelFailureKind.INVALID_RESPONSE, "invalid proposal envelope", False))
        object.__setattr__(self, "last_metadata", outcome.metadata)
        if outcome.outcome.context_id != context.context_id:
            return _failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "proposal context is stale", False))
        return outcome.outcome


def _build_request(
    context: AgentContext,
    *,
    include_serialized_context: bool = True,
) -> ModelDecisionRequest:
    suffix = hashlib.sha256(context.context_id.encode()).hexdigest()[:24]
    return ModelDecisionRequest(
        request_id=f"objective-request:{suffix}",
        serialized_context=(serialize_agent_context(context) if include_serialized_context else ""),
        schema_version=OBJECTIVE_SCHEMA_VERSION,
        instructions=_OBJECTIVE_INSTRUCTIONS,
        decision_schema=local_objective_response_schema(),
        image_inputs=context.image_inputs,
        agent_context=context,
    )


def _failure(failure: ModelFailure) -> PolicyFailure:
    return PolicyFailure(failure.kind, _PUBLIC_FAILURES[failure.kind], failure.retryable)
