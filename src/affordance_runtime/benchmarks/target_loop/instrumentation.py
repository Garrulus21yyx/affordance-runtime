"""Harness-only call-boundary instrumentation; counters never affect Runtime behavior."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from affordance_runtime.agent.decisions import LocalToolResult, RequestObservation, SelectAction
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.benchmarks.target_loop.contracts import CaseFailureOrigin
from affordance_runtime.benchmarks.target_loop.failure_origin import observation_failure_origin
from affordance_runtime.benchmarks.target_loop.metric_registry import require_custom_metric_name
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus, ExecutionOutcome
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.evaluator import ModelPortSemanticCriterionJudge
from affordance_runtime.model.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.contracts import ModelMetadata
from affordance_runtime.world import AcquisitionStatus, ObservationAcquisition


@dataclass
class BenchmarkInstrumentation:
    policy_calls: int = 0
    policy_schema_repair_count: int = 0
    goal_compiler_calls: int = 0
    goal_compiler_provider_attempts: int = 0
    goal_compiler_schema_repair_count: int = 0
    goal_compiler_contract_repair_count: int = 0
    goal_compiler_ready_count: int = 0
    goal_compiler_unavailable_count: int = 0
    tool_argument_repair_count: int = 0
    valid_tool_call_count: int = 0
    zero_tool_call_count: int = 0
    multiple_tool_call_count: int = 0
    unknown_tool_call_count: int = 0
    invalid_tool_argument_count: int = 0
    stale_tool_catalog_count: int = 0
    tool_grounding_gap_count: int = 0
    tool_catalog_count: int = 0
    tool_catalog_bytes: int = 0
    action_evaluator_calls: int = 0
    task_evaluator_calls: int = 0
    provider_attempts: int = 0
    provider_retry_count: int = 0
    fallback_count: int = 0
    configured_provider_retry_count: int | None = None
    semantic_judge_calls: int = 0
    confirmations_submitted: int = 0
    environment_execute_calls: int = 0
    effectful_dispatches: int = 0
    stale_opportunities: int = 0
    stale_zero_call_violations: int = 0
    forbidden_effect_attempts: int = 0
    duplicate_unknown_attempts: int = 0
    custom_metrics: dict[str, int | float] = field(default_factory=dict)
    model_metadata: ModelMetadata | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_latency_ms: float = 0.0
    failure_origin: CaseFailureOrigin = CaseFailureOrigin.NONE
    failure_code: str = ""
    exception_class: str = ""
    cleanup_failure_code: str = ""
    cleanup_exception_class: str = ""
    cleanup_failures: int = 0
    watchdog_code: str = ""
    watchdog_exception_class: str = ""
    environment_reset_acquisitions: int = 0
    environment_capture_calls: int = 0
    environment_post_acquisitions: int = 0
    currentness_probe_count: int = 0
    trace_recorder: RunTraceRecorder = field(default_factory=RunTraceRecorder)
    _unknown_attempts: set[str] = field(default_factory=set, repr=False)
    _policy_trace: list[dict[str, object]] = field(default_factory=list, repr=False)

    @property
    def policy_trace(self) -> list[dict[str, object]]:
        return [dict(event) for event in self._policy_trace]

    @property
    def trace_path(self) -> str:
        return str(self.trace_recorder.path) if self.trace_recorder.path is not None else ""

    def run_started(self, task, state) -> None:
        self.trace_recorder.run_started(task, state)

    def run_start_failed(self, task, acquisition) -> None:
        self.trace_recorder.run_start_failed(task, acquisition)

    def goal_compiler_completed(self, diagnostic) -> None:
        self.trace_recorder.goal_compiler_completed(diagnostic)
        self.goal_compiler_calls += 1
        self.goal_compiler_provider_attempts += int(
            diagnostic.get("provider_attempt_count", 0)
        )
        self.goal_compiler_schema_repair_count += int(
            diagnostic.get("schema_repair_count", 0)
        )
        self.goal_compiler_contract_repair_count += int(
            diagnostic.get("contract_repair_count", 0)
        )
        disposition = diagnostic.get("final_disposition")
        self.goal_compiler_ready_count += int(disposition == "ready")
        self.goal_compiler_unavailable_count += int(
            disposition in {"unsupported", "failed"}
        )

    def model_turn(self, context, outcome, policy, *, exception: str = "") -> None:
        self.trace_recorder.model_turn(context, outcome, policy, exception=exception)
        self._policy_trace.append(
            _policy_trace_event(
                self.policy_calls, context, outcome, policy, exception=exception
            )
        )

    def step_completed(self, step_number: int, result) -> None:
        self.trace_recorder.step_completed(step_number, result)

    def run_paused(self, state) -> None:
        self.trace_recorder.run_paused(state)

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        self.trace_recorder.run_resumed(kind, details)

    def run_error(self, error: BaseException, state) -> None:
        self.trace_recorder.run_error(error, state)

    def run_finished(self, state) -> None:
        self.trace_recorder.run_finished(state)

    def increment(self, name: str, value: int = 1) -> None:
        require_custom_metric_name(name)
        if type(value) is not int or value < 0:
            raise ValueError("custom metric increments must be non-negative integers")
        self.custom_metrics[name] = self.custom_metrics.get(name, 0) + value

    def set_custom_metric(self, name: str, value: int | float) -> None:
        require_custom_metric_name(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("custom metrics must be numeric")
        if not math.isfinite(value) or value < 0:
            raise ValueError("custom metrics must be finite and non-negative")
        self.custom_metrics[name] = value

    def record_failure(self, origin: CaseFailureOrigin, code: str, exception: Exception) -> None:
        if origin in {CaseFailureOrigin.HARNESS_WATCHDOG, CaseFailureOrigin.CLEANUP}:
            raise ValueError("watchdog and cleanup facts have dedicated owners")
        if self.failure_origin is CaseFailureOrigin.NONE:
            self.failure_origin = origin
            self.failure_code = code
            self.exception_class = type(exception).__name__

    def record_watchdog(self, code: str, exception: Exception) -> None:
        if not self.watchdog_code:
            self.watchdog_code = code
            self.watchdog_exception_class = type(exception).__name__

    def record_cleanup_failure(self, code: str, exception: Exception) -> None:
        if self.cleanup_failures:
            return
        self.cleanup_failures = 1
        self.cleanup_failure_code = code
        self.cleanup_exception_class = type(exception).__name__


@dataclass
class CountingPolicy:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    async def decide(self, context):
        self.instrumentation.policy_calls += 1
        try:
            outcome = await self.wrapped.decide(context)
        except Exception as exc:
            self.instrumentation.record_failure(
                CaseFailureOrigin.POLICY_DECISION, "policy_exception", exc
            )
            raise
        metadata = getattr(self.wrapped, "last_metadata", None)
        if isinstance(metadata, ModelMetadata):
            self.instrumentation.model_metadata = metadata
            self.instrumentation.prompt_tokens += metadata.prompt_tokens
            self.instrumentation.completion_tokens += metadata.completion_tokens
            self.instrumentation.total_tokens += metadata.total_tokens
            self.instrumentation.model_latency_ms += metadata.latency_ms
        return outcome


def _policy_trace_event(call: int, context, outcome, policy, *, exception: str = ""):
    event: dict[str, object] = {
        "policy_call": call,
        "context_id": context.context_id,
        "visible_action_count": len(context.actions.options),
        "selected_source_modalities": tuple(source.modality for source in context.actor_world.sources),
        "recent_step_count": len(context.recent_steps.items),
        "provider_attempts": tuple(
            {
                "attempt_number": item.attempt_number,
                "profile_index": item.profile_index,
                "status": item.status.value,
                "failure_kind": item.failure_kind.value if item.failure_kind is not None else "",
                "failure_code": item.failure_code.value if item.failure_code is not None else "",
                "origin": item.origin.value,
                "network_dispatched": item.origin.value == "network",
                "scheduled_delay_s": item.scheduled_delay_s,
                "response_id": item.response_id,
            }
            for item in getattr(_model_backed_policy(policy), "last_provider_attempts", ())
        ),
        "exception": exception,
    }
    if context.recent_steps.items:
        latest_step = context.recent_steps.items[-1]
        tool_result = latest_step.semantic_summary.get("result")
        if isinstance(tool_result, Mapping):
            event["previous_runtime_tool_result"] = to_json_compatible(tool_result)
    adapter = _dynamic_tool_adapter(policy)
    if adapter is not None:
        image_input_count = int(getattr(adapter, "last_image_input_count", len(context.image_inputs)))
        event["interaction_protocol"] = getattr(adapter, "interaction_protocol", "unknown")
        event["tool_transport"] = getattr(getattr(adapter, "transport_kind", None), "value", "")
        event["tool_resolution_code"] = getattr(
            getattr(adapter, "last_resolution_code", None),
            "value",
            "",
        )
        event["tool_catalog_count"] = int(getattr(adapter, "last_catalog_count", 0))
        event["tool_catalog_bytes"] = int(getattr(adapter, "last_catalog_bytes", 0))
        event["tool_argument_repair_count"] = int(getattr(adapter, "last_argument_repair_count", 0))
        event["tool_argument_violation_code"] = str(getattr(adapter, "last_argument_violation_code", ""))
        event["tool_argument_violation_paths"] = tuple(getattr(adapter, "last_argument_violation_paths", ()))
        event["tool_argument_selected_operation"] = str(getattr(adapter, "last_selected_operation", ""))
        event["tool_argument_repaired_operation_match"] = bool(getattr(adapter, "last_repaired_operation_match", False))
        event["tool_routing_normalization"] = str(getattr(adapter, "last_routing_normalization", ""))
        event["tool_routing_original_operation"] = str(getattr(adapter, "last_routing_original_operation", ""))
        event["tool_routing_normalized_operation"] = str(getattr(adapter, "last_routing_normalized_operation", ""))
        event["model_image_input_count"] = image_input_count
        event["policy_model_call_count"] = int(getattr(adapter, "last_model_call_count", 0))
        event["generation_attempts"] = to_json_compatible(
            getattr(adapter, "last_generation_attempts", ())
        )
        event["structured_output_validation_stage"] = "provider_response_to_grounded_command"
        event["structured_output_violations"] = tuple(
            {"field_path": item.field_path, "code": item.code}
            for item in getattr(adapter, "last_structured_output_violations", ())
        )
        event["structured_output_repair_attempted"] = bool(
            getattr(adapter, "last_structured_output_repair_attempted", False)
        )
        event["structured_output_repair_failed"] = bool(getattr(adapter, "last_structured_output_repair_failed", False))
    decision = outcome
    if isinstance(decision, (SelectAction, RequestObservation, LocalToolResult)):
        event["outcome"] = type(decision).__name__
        event["decision"] = _decision_trace(decision)
        if isinstance(decision, SelectAction):
            selected = _selected_grounding_trace(
                context,
                decision,
                image_attached=bool(getattr(adapter, "last_image_input_count", len(context.image_inputs))),
            )
            if selected is not None:
                event["selected_grounding"] = selected
    elif isinstance(decision, PolicyFailure):
        event["outcome"] = "policy_failure"
        event["policy_failure"] = {
            "kind": str(decision.kind),
            "retryable": decision.retryable,
        }
    else:
        event["outcome"] = "exception" if exception else type(decision).__name__
    return event


def _dynamic_tool_adapter(value):
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if hasattr(item, "last_resolution_code") and hasattr(item, "last_catalog_count"):
            return item
        wrapped = getattr(item, "wrapped", None)
        port = getattr(item, "port", None)
        ports = getattr(item, "ports", None)
        if wrapped is not None:
            pending.append(wrapped)
        if port is not None:
            pending.append(port)
        if isinstance(ports, tuple):
            pending.extend(ports)
    return None


def _model_backed_policy(value):
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, ModelBackedAgentPolicy):
            return item
        wrapped = getattr(item, "wrapped", None)
        if wrapped is not None:
            pending.append(wrapped)
    return value


def _selected_grounding_trace(context, decision, *, image_attached: bool):
    action_id = getattr(decision, "action_id", "")
    if not action_id:
        return None
    option = next((item for item in context.actions.options if item.action_id == action_id), None)
    if option is None:
        return None
    ref = context.grounding.target_refs.get(option.target_id)
    entity = next((item for item in context.grounding.entities if item.ref == ref), None)
    if entity is None:
        return None
    return {
        "ref": entity.ref,
        "role": entity.role,
        "label": entity.label,
        "state": to_json_compatible(entity.state),
        "marked": entity.marked and image_attached,
        "semantic_action": option.semantic_action,
    }


def _decision_trace(decision):
    value: dict[str, object] = {"kind": type(decision).__name__, "context_id": decision.context_id}
    for name in (
        "action_id",
        "destination_id",
        "subject_id",
        "purpose",
        "evidence_property",
        "relevance_role",
        "cursor",
        "category",
        "tool_name",
        "arguments",
    ):
        item = getattr(decision, name, None)
        if item not in (None, ""):
            value[name] = item.value if hasattr(item, "value") else item
    return value


@dataclass
class CountingActionEvaluator:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def evaluate(self, task, before, request, result, after):
        self.instrumentation.action_evaluator_calls += 1
        try:
            return await self.wrapped.evaluate(task, before, request, result, after)
        except Exception as exc:
            self.instrumentation.record_failure(
                CaseFailureOrigin.ACTION_EVALUATION,
                "action_evaluator_exception",
                exc,
            )
            raise


@dataclass
class CountingTaskEvaluator:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    async def evaluate(self, task, observation):
        self.instrumentation.task_evaluator_calls += 1
        try:
            return await self.wrapped.evaluate(task, observation)
        except Exception as exc:
            self.instrumentation.record_failure(
                CaseFailureOrigin.TASK_EVALUATION,
                "task_evaluator_exception",
                exc,
            )
            raise


@dataclass
class CountingDecisionPort:
    wrapped: object
    instrumentation: BenchmarkInstrumentation

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    @property
    def transport_timeout_s(self):
        return getattr(self.wrapped, "transport_timeout_s", None)

    async def generate(self, request):
        try:
            return await self.wrapped.generate(request)
        finally:
            attempts = tuple(getattr(self.wrapped, "last_attempts", ()))
            attempt_count = len(attempts) or 1
            schema_repairs = _decision_schema_repair_count(self.wrapped)
            model_calls = _decision_model_call_count(self.wrapped)
            self.instrumentation.provider_attempts += max(model_calls, attempt_count + schema_repairs)
            self.instrumentation.policy_schema_repair_count += schema_repairs
            _record_dynamic_tool_metrics(self.instrumentation, self.wrapped)
            explicit_retries = getattr(self.wrapped, "last_provider_retry_count", None)
            self.instrumentation.provider_retry_count += (
                int(explicit_retries)
                if explicit_retries is not None
                else max(0, attempt_count - 1)
            )
            self.instrumentation.fallback_count += int(getattr(self.wrapped, "last_fallback_count", 0))


def _decision_schema_repair_count(port: object) -> int:
    values = getattr(port, "ports", None)
    if isinstance(values, tuple):
        return sum(int(getattr(item, "last_schema_repair_count", 0)) for item in values)
    return int(getattr(port, "last_schema_repair_count", 0))


def _decision_model_call_count(port: object) -> int:
    values = getattr(port, "ports", None)
    if isinstance(values, tuple):
        return sum(int(getattr(item, "last_model_call_count", 0)) for item in values)
    return int(getattr(port, "last_model_call_count", 0))


def _record_dynamic_tool_metrics(instrumentation, port: object) -> None:
    values = getattr(port, "ports", None)
    adapters = values if isinstance(values, tuple) else (port,)
    for adapter in adapters:
        code = getattr(getattr(adapter, "last_resolution_code", None), "value", "")
        field = {
            "accepted": "valid_tool_call_count",
            "zero_tool_calls": "zero_tool_call_count",
            "multiple_tool_calls": "multiple_tool_call_count",
            "unknown_tool": "unknown_tool_call_count",
            "invalid_tool_arguments": "invalid_tool_argument_count",
            "unknown_tool_destination": "invalid_tool_argument_count",
            "stale_tool_catalog": "stale_tool_catalog_count",
            "tool_grounding_gap": "tool_grounding_gap_count",
        }.get(code)
        if field is not None:
            setattr(instrumentation, field, getattr(instrumentation, field) + 1)
        instrumentation.tool_catalog_count += int(getattr(adapter, "last_catalog_count", 0))
        instrumentation.tool_catalog_bytes += int(getattr(adapter, "last_catalog_bytes", 0))
        instrumentation.tool_argument_repair_count += int(getattr(adapter, "last_argument_repair_count", 0))


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

    @property
    def observation_capabilities(self):
        return self.wrapped.observation_capabilities

    async def reset(self, task):
        try:
            acquisition = await self.wrapped.reset(task)
        except Exception as exc:
            self.instrumentation.record_failure(CaseFailureOrigin.ENVIRONMENT_RESET, "reset_exception", exc)
            raise
        if isinstance(acquisition, ObservationAcquisition):
            self.instrumentation.environment_reset_acquisitions += 1
        return acquisition

    async def revise_task(self, task):
        return await self.wrapped.revise_task(task)

    async def capture(self, request):
        self.instrumentation.environment_capture_calls += 1
        try:
            acquisition = await self.wrapped.capture(request)
        except Exception as exc:
            origin = observation_failure_origin(request.kind)
            self.instrumentation.record_failure(origin, "capture_exception", exc)
            raise
        if isinstance(acquisition, ObservationAcquisition):
            return acquisition
        return acquisition

    async def execute(self, request):
        state = self.instrumentation
        state.environment_execute_calls += 1
        before = _executed_count(self.wrapped)
        identity = _attempt_identity(request)
        if set(request.selection.semantic_effects) & self.forbidden_effects:
            state.forbidden_effect_attempts += 1
        try:
            outcome = await self.wrapped.execute(request)
        except Exception as exc:
            state.record_failure(CaseFailureOrigin.EXECUTION, "execution_exception", exc)
            raise
        if not isinstance(outcome, ExecutionOutcome):
            return outcome
        result = outcome.result
        if not isinstance(result, ActionResult):
            return outcome
        if isinstance(outcome.post_acquisition, ObservationAcquisition):
            state.environment_post_acquisitions += int(
                outcome.post_acquisition.status
                in {AcquisitionStatus.ACQUIRED, AcquisitionStatus.FAILED}
            )
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
        return outcome

    def is_current(self, request):
        self.instrumentation.currentness_probe_count += 1
        return self.wrapped.is_current(request)


def instrument_policy(policy, instrumentation: BenchmarkInstrumentation):
    if isinstance(policy, ModelBackedAgentPolicy):
        instrumentation.configured_provider_retry_count = _configured_retry_count(
            policy.port,
        )
        policy = replace(policy, port=CountingDecisionPort(policy.port, instrumentation))
    elif isinstance(getattr(policy, "wrapped", None), ModelBackedAgentPolicy):
        inner = policy.wrapped
        instrumentation.configured_provider_retry_count = _configured_retry_count(
            inner.port,
        )
        policy = replace(
            policy,
            wrapped=replace(inner, port=CountingDecisionPort(inner.port, instrumentation)),
        )
    return CountingPolicy(policy, instrumentation)


def _configured_retry_count(port: object) -> int | None:
    configured = getattr(port, "configured_retry_count", None)
    if type(configured) is int:
        return configured
    config = getattr(port, "config", None)
    rate_limit = getattr(config, "rate_limit_retries", None)
    transient = getattr(config, "transient_retries", None)
    if type(rate_limit) is int and type(transient) is int:
        return rate_limit + transient
    return None


def instrument_task_evaluator(evaluator, instrumentation: BenchmarkInstrumentation):
    if isinstance(evaluator, ProductionTaskEvaluator) and evaluator.semantic_judge is not None:
        judge = evaluator.semantic_judge
        if isinstance(judge, ModelPortSemanticCriterionJudge):
            judge = replace(judge, port=CountingModelPort(judge.port, instrumentation))
        evaluator = replace(evaluator, semantic_judge=CountingSemanticJudge(judge, instrumentation))
    return CountingTaskEvaluator(evaluator, instrumentation)


def _executed_count(environment) -> int | None:
    requests = getattr(environment, "dispatched_requests", None)
    if requests is None:
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
