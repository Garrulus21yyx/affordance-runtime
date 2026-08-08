"""AgentPolicy implementation backed by one injected structured model call."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.agent.policy import AgentPolicyOutcome, PolicyFailure
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.contracts import ModelDecisionRequest, ModelDecisionResponse
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.port import StructuredDecisionModelPort
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS, SCHEMA_VERSION, decision_response_schema
from affordance_runtime.model_policy.serialization import serialize_agent_context

_PUBLIC_FAILURES = {
    ModelFailureKind.PROVIDER_UNAVAILABLE: "model decision provider is unavailable",
    ModelFailureKind.TIMEOUT: "model decision provider timed out",
    ModelFailureKind.INVALID_RESPONSE: "model decision response was invalid",
    ModelFailureKind.SCHEMA_ERROR: "model decision response violated the required schema",
    ModelFailureKind.REFUSED: "model decision provider refused the request",
    ModelFailureKind.INTERNAL_ERROR: "model decision could not be produced",
}


@dataclass(frozen=True)
class ModelBackedAgentPolicy:
    port: StructuredDecisionModelPort

    async def decide(self, context: AgentContext) -> AgentPolicyOutcome:
        try:
            request = _build_request(context)
            outcome = await self.port.generate(request)
        except TimeoutError:
            outcome = ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False)
        except Exception:
            outcome = ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "provider call failed", False)
        if isinstance(outcome, ModelFailure):
            return _policy_failure(outcome)
        if not isinstance(outcome, ModelDecisionResponse):
            failure = ModelFailure(ModelFailureKind.INVALID_RESPONSE, "provider returned an invalid envelope", False)
            return _policy_failure(failure)
        decision = parse_agent_decision(outcome.raw_payload, context.context_id)
        if isinstance(decision, ModelFailure):
            return _policy_failure(decision)
        return decision


def _build_request(context: AgentContext) -> ModelDecisionRequest:
    suffix = hashlib.sha256(context.context_id.encode()).hexdigest()[:24]
    return ModelDecisionRequest(
        request_id=f"model-request:{suffix}",
        serialized_context=serialize_agent_context(context),
        schema_version=SCHEMA_VERSION,
        instructions=MODEL_POLICY_INSTRUCTIONS,
        decision_schema=decision_response_schema(),
    )


def _policy_failure(failure: ModelFailure) -> PolicyFailure:
    return PolicyFailure(failure.kind, _PUBLIC_FAILURES[failure.kind], failure.retryable)
