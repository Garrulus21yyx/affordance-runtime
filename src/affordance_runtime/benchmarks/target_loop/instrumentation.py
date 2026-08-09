"""Harness-only call-boundary instrumentation; counters never affect Runtime behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.execution import ActionError, DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_evaluator import ModelPortSemanticCriterionJudge
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.contracts import ModelMetadata


@dataclass
class BenchmarkInstrumentation:
    policy_calls: int = 0
    action_evaluator_calls: int = 0
    task_evaluator_calls: int = 0
    provider_attempts: int = 0
    semantic_judge_calls: int = 0
    confirmations_submitted: int = 0
    environment_execute_calls: int = 0
    effectful_dispatches: int = 0
    stale_opportunities: int = 0
    stale_zero_call_violations: int = 0
    forbidden_effect_attempts: int = 0
    duplicate_unknown_attempts: int = 0
    custom_metrics: dict[str, int] = field(default_factory=dict)
    model_metadata: ModelMetadata | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_latency_ms: float = 0.0
    _unknown_attempts: set[str] = field(default_factory=set, repr=False)

    def increment(self, name: str, value: int = 1) -> None:
        self.custom_metrics[name] = self.custom_metrics.get(name, 0) + value


@dataclass
class CountingPolicy:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def decide(self, context):
        self.instrumentation.policy_calls += 1
        outcome = await self.wrapped.decide(context)
        metadata = getattr(self.wrapped, "last_metadata", None)
        if isinstance(metadata, ModelMetadata):
            self.instrumentation.model_metadata = metadata
            self.instrumentation.prompt_tokens += metadata.prompt_tokens
            self.instrumentation.completion_tokens += metadata.completion_tokens
            self.instrumentation.total_tokens += metadata.total_tokens
            self.instrumentation.model_latency_ms += metadata.latency_ms
        return outcome


@dataclass
class CountingActionEvaluator:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def evaluate(self, task, before, request, result, after):
        self.instrumentation.action_evaluator_calls += 1
        return await self.wrapped.evaluate(task, before, request, result, after)


@dataclass
class CountingTaskEvaluator:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def evaluate(self, task, observation):
        self.instrumentation.task_evaluator_calls += 1
        return await self.wrapped.evaluate(task, observation)


@dataclass
class CountingDecisionPort:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    @property
    def transport_timeout_s(self):
        return getattr(self.wrapped, "transport_timeout_s", None)

    async def generate(self, request):
        self.instrumentation.provider_attempts += 1
        return await self.wrapped.generate(request)


@dataclass
class CountingModelPort:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    async def generate_structured(self, messages, output_schema, config):
        self.instrumentation.provider_attempts += 1
        return await self.wrapped.generate_structured(messages, output_schema, config)


@dataclass
class CountingSemanticJudge:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def evaluate(self, request):
        self.instrumentation.semantic_judge_calls += 1
        return await self.wrapped.evaluate(request)


@dataclass
class CountingEnvironment:
    wrapped: object
    instrumentation: BenchmarkInstrumentation
    forbidden_effects: frozenset[str]

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    async def reset(self, task):
        return await self.wrapped.reset(task)

    async def observe(self, reason):
        return await self.wrapped.observe(reason)

    async def execute(self, request):
        state = self.instrumentation
        state.environment_execute_calls += 1
        before = _executed_count(self.wrapped)
        identity = _attempt_identity(request)
        if set(request.selection.semantic_effects) & self.forbidden_effects:
            state.forbidden_effect_attempts += 1
        result = await self.wrapped.execute(request)
        dispatches = _dispatch_count(self.wrapped, before, result)
        if result.error in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
            state.stale_opportunities += 1
            state.stale_zero_call_violations += dispatches
        if dispatches:
            if identity in state._unknown_attempts:
                state.duplicate_unknown_attempts += 1
            state.effectful_dispatches += dispatches
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN:
            state._unknown_attempts.add(identity)
        return result


def instrument_policy(policy, instrumentation: BenchmarkInstrumentation):
    if isinstance(policy, ModelBackedAgentPolicy):
        policy = replace(policy, port=CountingDecisionPort(policy.port, instrumentation))
    elif isinstance(getattr(policy, "wrapped", None), ModelBackedAgentPolicy):
        inner = policy.wrapped
        policy = replace(
            policy,
            wrapped=replace(inner, port=CountingDecisionPort(inner.port, instrumentation)),
        )
    return CountingPolicy(policy, instrumentation)


def instrument_task_evaluator(evaluator, instrumentation: BenchmarkInstrumentation):
    if isinstance(evaluator, ProductionTaskEvaluator) and evaluator.semantic_judge is not None:
        judge = evaluator.semantic_judge
        if isinstance(judge, ModelPortSemanticCriterionJudge):
            judge = replace(judge, port=CountingModelPort(judge.port, instrumentation))
        evaluator = replace(evaluator, semantic_judge=CountingSemanticJudge(judge, instrumentation))
    return CountingTaskEvaluator(evaluator, instrumentation)


def _executed_count(environment) -> int | None:
    requests = getattr(environment, "executed_requests", None)
    return len(requests) if isinstance(requests, list) else None


def _dispatch_count(environment, before: int | None, result) -> int:
    after = _executed_count(environment)
    if before is not None and after is not None:
        return max(0, after - before)
    evidence = result.adapter_evidence.get("effectful_dispatch_count")
    if isinstance(evidence, int) and not isinstance(evidence, bool):
        return max(0, evidence)
    return int(result.dispatch_status != DispatchStatus.NOT_SENT)


def _attempt_identity(request) -> str:
    payload = {
        "action": request.intent.semantic_action,
        "target": request.intent.target_id,
        "destination": request.intent.destination_id,
        "parameters": to_json_compatible(request.intent.parameters),
        "effects": request.selection.semantic_effects,
        "risk": str(request.selection.risk),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
