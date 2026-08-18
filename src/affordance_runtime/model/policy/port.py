"""One-call provider-neutral ports for typed model phases."""

from typing import Protocol, TypeVar

from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ModelInvocationResult,
    ResolvedModelDecision,
)

ResolvedT_co = TypeVar("ResolvedT_co", covariant=True)


class StructuredModelPort(Protocol[ResolvedT_co]):
    async def generate(
        self, request: ModelDecisionRequest
    ) -> ModelInvocationResult[ResolvedT_co]: ...


class StructuredDecisionModelPort(StructuredModelPort[ResolvedModelDecision], Protocol):
    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]: ...
