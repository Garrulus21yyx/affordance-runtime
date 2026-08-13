"""AgentPolicy implementation backed by one injected structured model call."""

from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from affordance_runtime.agent.policy import AgentPolicyOutcome, PolicyFailure
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.contracts import ModelDecisionRequest, ModelDecisionResponse, ModelMetadata
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.port import StructuredDecisionModelPort
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS, SCHEMA_VERSION, decision_response_schema
from affordance_runtime.model_policy.serialization import serialize_agent_context
from affordance_runtime.task.semantic_validation import TaskSemanticValidatorPort

_PUBLIC_FAILURES = {
    ModelFailureKind.PROVIDER_UNAVAILABLE: "model decision provider is unavailable",
    ModelFailureKind.PROVIDER_EXHAUSTED: "model decision providers exhausted bounded recovery",
    ModelFailureKind.TIMEOUT: "model decision provider timed out",
    ModelFailureKind.INVALID_RESPONSE: "model decision response was invalid",
    ModelFailureKind.SCHEMA_ERROR: "model decision response violated the required schema",
    ModelFailureKind.REFUSED: "model decision provider refused the request",
    ModelFailureKind.INTERNAL_ERROR: "model decision could not be produced",
}


@dataclass(frozen=True)
class ModelBackedAgentPolicy:
    port: StructuredDecisionModelPort
    call_timeout_s: float = 90.0
    last_metadata: ModelMetadata | None = field(default=None, init=False, compare=False)
    last_provider_attempts: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_fallback_count: int = field(default=0, init=False, compare=False)
    semantic_validator: TaskSemanticValidatorPort | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not 0 < self.call_timeout_s <= 300:
            raise ValueError("model policy call timeout must be in (0, 300]")
        transport_timeout = getattr(self.port, "transport_timeout_s", None)
        if transport_timeout is not None and transport_timeout >= self.call_timeout_s:
            raise ValueError("model transport timeout must be strictly below the policy deadline")

    async def decide(self, context: AgentContext) -> AgentPolicyOutcome:
        object.__setattr__(self, "last_metadata", None)
        object.__setattr__(self, "last_provider_attempts", ())
        object.__setattr__(self, "last_fallback_count", 0)
        try:
            request = _build_request(context)
        except Exception:
            return _policy_failure(ModelFailure(ModelFailureKind.INTERNAL_ERROR, "request construction failed", False))
        try:
            outcome = await _generate_with_deadline(self.port, request, self.call_timeout_s)
        except TimeoutError:
            return _policy_failure(ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False))
        except Exception:
            return _policy_failure(ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "provider call failed", False))
        finally:
            object.__setattr__(
                self,
                "last_provider_attempts",
                tuple(getattr(self.port, "last_attempts", ())),
            )
            object.__setattr__(
                self,
                "last_fallback_count",
                int(getattr(self.port, "last_fallback_count", 0)),
            )
        if isinstance(outcome, ModelFailure):
            return _policy_failure(outcome)
        if not isinstance(outcome, ModelDecisionResponse):
            failure = ModelFailure(ModelFailureKind.INVALID_RESPONSE, "provider returned an invalid envelope", False)
            return _policy_failure(failure)
        object.__setattr__(self, "last_metadata", outcome.metadata)
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
        image_inputs=context.image_inputs,
        policy_context=context,
    )


async def _generate_with_deadline(
    port: StructuredDecisionModelPort,
    request: ModelDecisionRequest,
    timeout_s: float,
) -> ModelDecisionResponse | ModelFailure:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if task is None:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-policy-deadline") as worker:
            future = worker.submit(asyncio.run, _bounded_generate(port, request, timeout_s))
            return future.result(timeout=timeout_s + 1.0)
    return await _bounded_generate(port, request, timeout_s)


async def _bounded_generate(
    port: StructuredDecisionModelPort,
    request: ModelDecisionRequest,
    timeout_s: float,
) -> ModelDecisionResponse | ModelFailure:
    return await asyncio.wait_for(port.generate(request), timeout=timeout_s)


def _policy_failure(failure: ModelFailure) -> PolicyFailure:
    return PolicyFailure(failure.kind, _PUBLIC_FAILURES[failure.kind], failure.retryable)
