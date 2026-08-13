"""One-call provider-neutral port for structured agent decisions."""

from typing import Protocol

from affordance_runtime.model_boundary.failures import ModelFailure
from affordance_runtime.model_policy.contracts import ModelDecisionRequest, ResolvedModelDecision


class StructuredDecisionModelPort(Protocol):
    async def generate(
        self, request: ModelDecisionRequest
    ) -> ResolvedModelDecision | ModelFailure: ...
