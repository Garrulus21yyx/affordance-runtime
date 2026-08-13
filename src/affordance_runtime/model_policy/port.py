"""One-call provider-neutral ports for typed model phases."""

from typing import Protocol, TypeVar

from affordance_runtime.model_boundary.failures import ModelFailure
from affordance_runtime.model_policy.contracts import (
    ModelDecisionRequest,
    ResolvedLocalObjectiveProposal,
    ResolvedModelDecision,
)

ResolvedT_co = TypeVar(
    "ResolvedT_co",
    ResolvedModelDecision,
    ResolvedLocalObjectiveProposal,
    covariant=True,
)


class StructuredModelPort(Protocol[ResolvedT_co]):
    async def generate(
        self, request: ModelDecisionRequest
    ) -> ResolvedT_co | ModelFailure: ...


class StructuredDecisionModelPort(StructuredModelPort[ResolvedModelDecision], Protocol):
    pass


class StructuredObjectiveModelPort(StructuredModelPort[ResolvedLocalObjectiveProposal], Protocol):
    pass
