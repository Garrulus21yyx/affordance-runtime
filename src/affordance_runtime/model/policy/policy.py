"""AgentPolicy implementation backed by one injected structured model call."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import (
    DecisionCapability,
    normalize_decision_capabilities,
)
from affordance_runtime.agent.policy import AgentPolicyOutcome, PolicyFailure
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from affordance_runtime.model.policy.port import StructuredDecisionModelPort

_PUBLIC_FAILURES = {
    ModelFailureKind.PROVIDER_UNAVAILABLE: "model decision provider is unavailable",
    ModelFailureKind.PROVIDER_EXHAUSTED: "model decision providers exhausted bounded recovery",
    ModelFailureKind.TIMEOUT: "model decision provider timed out",
    ModelFailureKind.INVALID_RESPONSE: "model decision response was invalid",
    ModelFailureKind.SCHEMA_ERROR: "model decision response violated the required schema",
    ModelFailureKind.INVALID_TOOL_ARGUMENTS: "model decision referenced invalid tool arguments",
    ModelFailureKind.TOOL_GROUNDING_GAP: "model decision referenced unavailable grounding evidence",
    ModelFailureKind.REFUSED: "model decision provider refused the request",
    ModelFailureKind.CONTEXT_CAPACITY: "model decision request exceeded context capacity",
    ModelFailureKind.INTERNAL_ERROR: "model decision could not be produced",
}


@dataclass(frozen=True)
class ModelBackedAgentPolicy:
    port: StructuredDecisionModelPort
    call_timeout_s: float = 90.0
    last_invocation_result: ModelInvocationResult[ResolvedModelDecision] | None = field(
        default=None, init=False, compare=False
    )
    last_fallback_count: int = field(default=0, init=False, compare=False)

    def __post_init__(self) -> None:
        if not 0 < self.call_timeout_s <= 300:
            raise ValueError("model policy call timeout must be in (0, 300]")
        transport_timeout = getattr(self.port, "transport_timeout_s", None)
        if transport_timeout is not None and transport_timeout >= self.call_timeout_s:
            raise ValueError("model transport timeout must be strictly below the policy deadline")
        semantic_timeout_budget = getattr(self.port, "semantic_timeout_budget_s", None)
        if semantic_timeout_budget is not None and semantic_timeout_budget >= self.call_timeout_s:
            raise ValueError("model semantic timeout budget must be below the policy deadline")
        configured_policy_timeout = getattr(self.port, "policy_timeout_s", None)
        if (
            configured_policy_timeout is not None
            and configured_policy_timeout != self.call_timeout_s
        ):
            raise ValueError("model port and policy deadlines must agree")

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return normalize_decision_capabilities(
            getattr(self.port, "supported_decisions", frozenset()),
            field_name="decision model port supported_decisions",
        )

    @property
    def last_metadata(self) -> ModelMetadata | None:
        result = self.last_invocation_result
        return result.metadata if result is not None else None

    @property
    def last_provider_attempts(self):
        result = self.last_invocation_result
        return result.attempts if result is not None else ()

    async def decide(self, context: AgentContext) -> AgentPolicyOutcome:
        object.__setattr__(self, "last_invocation_result", None)
        object.__setattr__(self, "last_fallback_count", 0)
        try:
            request = _build_request(context)
        except Exception:
            return _policy_failure(ModelFailure(ModelFailureKind.INTERNAL_ERROR, "request construction failed", False))
        try:
            outcome = await _generate_with_deadline(self.port, request, self.call_timeout_s)
        except TimeoutError:
            failure = ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False)
            invocation = _failure_invocation_from_port(self.port, failure)
            object.__setattr__(self, "last_invocation_result", invocation)
            return _policy_failure(failure)
        except Exception:
            failure = ModelFailure(ModelFailureKind.INTERNAL_ERROR, "decision port failed", False)
            invocation = _failure_invocation_from_port(self.port, failure)
            object.__setattr__(self, "last_invocation_result", invocation)
            return _policy_failure(failure)
        finally:
            object.__setattr__(
                self,
                "last_fallback_count",
                int(getattr(self.port, "last_fallback_count", 0)),
            )
        if not isinstance(outcome, ModelInvocationResult):
            failure = ModelFailure(
                ModelFailureKind.INVALID_RESPONSE,
                "provider returned an invalid envelope",
                False,
            )
            invocation = ModelInvocationResult(failure=failure)
            object.__setattr__(self, "last_invocation_result", invocation)
            return _policy_failure(failure)
        invocation = outcome
        object.__setattr__(self, "last_invocation_result", invocation)
        if invocation.failure is not None:
            return _policy_failure(invocation.failure)
        outcome = invocation.output
        if outcome.decision.context_id != context.context_id:
            return _policy_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "decision context is stale", False))
        return outcome.decision

    def close_deferred_call(self, step: object) -> None:
        close = getattr(self.port, "close_deferred_call", None)
        if callable(close):
            close(step)

    def export_checkpoint_history(self) -> Mapping[str, object]:
        exporter = getattr(self.port, "export_checkpoint_history", None)
        if not callable(exporter):
            raise TypeError("model port does not support checkpoint history")
        history = exporter()
        if not isinstance(history, Mapping):
            raise TypeError("model checkpoint history must be a mapping")
        return history


def _build_request(context: AgentContext) -> ModelDecisionRequest:
    suffix = hashlib.sha256(context.context_id.encode()).hexdigest()[:24]
    return ModelDecisionRequest(
        request_id=f"model-request:{suffix}",
        agent_context=context,
        last_step=context.last_step,
    )


async def _generate_with_deadline(
    port: StructuredDecisionModelPort,
    request: ModelDecisionRequest,
    timeout_s: float,
) -> ModelInvocationResult[ResolvedModelDecision]:
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
) -> ModelInvocationResult[ResolvedModelDecision]:
    return await asyncio.wait_for(port.generate(request), timeout=timeout_s)


def _failure_invocation_from_port(
    port: StructuredDecisionModelPort,
    failure: ModelFailure,
) -> ModelInvocationResult[ResolvedModelDecision]:
    existing = getattr(port, "last_invocation_result", None)
    if isinstance(existing, ModelInvocationResult):
        return existing
    return ModelInvocationResult(failure=failure)


def _policy_failure(failure: ModelFailure) -> PolicyFailure:
    return PolicyFailure(failure.kind, _PUBLIC_FAILURES[failure.kind], failure.retryable)
