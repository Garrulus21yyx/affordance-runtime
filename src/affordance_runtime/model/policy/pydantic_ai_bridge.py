"""PydanticAI bridge for one fresh-world grounded GUI decision.

PydanticAI owns provider adaptation, tool-call parsing, and call IDs.  Tools are
external/deferred because the GUI Runtime remains the only owner of binding,
execution, risk, observation, and evaluation.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from affordance_runtime.agent.attempt_signature import (
    PublicAttemptSignature,
    public_attempt_signature,
)
from affordance_runtime.agent.context.compact_world_renderer import DeliveryManifest
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.contracts import sanitize_history_value
from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.agent.context.model_turn_delivery import ModelTurnDelivery
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.decisions import (
    AgentDecision,
    DecisionKind,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    ToolRejectedResult,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.canonical_provider_envelope import (
    UNEXECUTED_TOOL_CALL_MESSAGE,
    CanonicalProviderEnvelope,
    CanonicalProviderEnvelopeBinder,
    CanonicalProviderIdentity,
    _project_pydantic_history,
)
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from affordance_runtime.model.policy.grounded_tool_catalog import (
    resolve_grounded_action_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_rejection import (
    grounded_tool_rejection_decision,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.prompt import MODEL_POLICY_EVIDENCE_STATUS
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyInvocationPhase,
    ActionPolicyReasoningPolicy,
)
from affordance_runtime.model.policy.request_admission import (
    AdmittedProviderEnvelope,
    InvalidProviderEnvelope,
    ModelRequestBreakdown,
    ModelRequestCapacityError,
    RejectedProviderEnvelope,
    RequestAdmission,
    request_breakdown_diagnostics,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.model.policy.turn_packer import TurnPacker
from affordance_runtime.model.providers.port import StructuredOutputFailureKind

_MAX_PROVIDER_RETRIES = 1
_DEFAULT_PROVIDER_BACKOFF_S = 1.0
_MAX_PROVIDER_BACKOFF_S = 5.0
_POLICY_DEADLINE_SAFETY_S = 0.5
_HISTORY_COMPACTION_SCHEMA = "pydantic-ai-harness.summarizing-compaction.v1"
_HISTORY_COMPACTION_PRESSURE_RATIO = 0.8
_HISTORY_ECONOMY_PRESSURE_RATIO = 0.5
_HISTORY_COMPACTION_TARGET_RATIO = 0.3
_HISTORY_COMPACTION_MIN_RECLAIM_RATIO = 0.15
_HISTORY_RECENT_EXACT_TOKENS_RATIO = 0.12
_HISTORY_COMPACTION_MAX_OUTPUT_TOKENS = 1024
_TASK_ANCHOR_METADATA_KEY = "affordance_runtime.task_anchor"
_HISTORY_COMPACTION_SUMMARY_PROMPT = f"""
You are compacting an expired prefix of a GUI agent trajectory. The summary replaces that
prefix, so preserve only information needed to continue the user's task correctly.

Use these exact headings, omitting empty sections:

## Completed outcomes
At most three stable user-requirement outcomes already completed. Record outcomes, not actions
taken, current stage, or a future plan.

## Verified facts
At most eight exact facts necessary for unfinished requirements or the final answer. Include a
short public document or tool-call source when present. Never promote an ambiguity or hypothesis.
Exact values that directly fill requested final-answer fields have highest priority and must be
retained before prerequisite or operational facts. Never omit such an output value in order to
retain current controls, form contents, selected modes, current locations, service restrictions,
or other execution setup.
Completed ToolReturns below are exact, bounded results that were visible to the ActionPolicy.
When a later ActionPolicy response explicitly concludes a task fact from a completed result,
preserve that latest conclusion unless a still-later result or response contradicts or retracts
it. Coverage or pagination metadata limits the result's scope; it does not invalidate complete
records or exact values already returned. A later navigation, lookup, or execution failure does
not retract an already supported fact unless it explicitly disproves that fact.

Shared evidence-status rule:
{MODEL_POLICY_EVIDENCE_STATUS}

## Failed strategies
At most two terse strategy-level failures worth avoiding. Never enumerate attempted URLs,
individual clicks, reads, tab switches, or other action history.

Fresh World supplied to the continuing agent is authoritative. Focus on conclusions and
outcomes rather than narrating steps. Do not preserve current URLs, stale loading state,
selectors, call-local E/R/F/N refs, old control IDs, or incidental page metadata. Do not write
remaining questions, working hypotheses, current stage, next intent, or any other prospective
task state: the continuing ActionPolicy derives its next action from the current TaskGoal,
GoalPlan, fresh World, and recent exact suffix. Keep the summary concise and respond with only
the summary.

<messages>
{{messages}}
</messages>
""".strip()
_HISTORY_COMPACTION_INSTRUCTIONS = (
    "Summarize only stable completed outcomes, verified facts, and failed strategies from an expired "
    "GUI-agent trajectory prefix; do not invent current or prospective task state."
)
if TYPE_CHECKING:
    from pydantic_ai.messages import ModelResponse


@dataclass(frozen=True)
class ConfiguredPydanticAIModel:
    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_multimodal: bool


@dataclass(frozen=True)
class _ProviderFailureDetail:
    code: ProviderFailureCode
    retryable: bool
    reason: str
    exception_class: str
    status_code: int | None = None
    retry_after_s: float | None = None


@dataclass(frozen=True)
class _HistoryCompactionRun:
    messages: tuple[object, ...]
    transcript: tuple[object, ...] = ()
    error: str = ""
    latency_ms: float = 0.0
    attempted: bool = False
    trigger: str = "token_pressure"


class _ProviderCallExhausted(RuntimeError):
    def __init__(self, detail: _ProviderFailureDetail) -> None:
        super().__init__(detail.reason)
        self.detail = detail


@dataclass(frozen=True)
class AcceptedToolExchange:
    """One selected call plus every exact proposal in bounded SDK history."""

    call: ToolCall
    decision: AgentDecision
    response: ModelResponse
    discarded_call_count: int = 0

    def __post_init__(self) -> None:
        from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart

        decision_call_id = str(getattr(self.decision, "tool_call_id", ""))
        if (
            not isinstance(self.call, ToolCall)
            or not isinstance(self.decision, AgentDecision)
            or not isinstance(self.response, ModelResponse)
            or type(self.discarded_call_count) is not int
            or self.discarded_call_count < 0
        ):
            raise TypeError("accepted tool exchange is not typed")
        response_calls = tuple(part for part in self.response.parts if isinstance(part, ToolCallPart))
        response_call_ids = tuple(part.tool_call_id for part in response_calls)
        if (
            any(not isinstance(part, (ThinkingPart, TextPart, ToolCallPart)) for part in self.response.parts)
            or len(response_calls) != self.discarded_call_count + 1
            or len(set(response_call_ids)) != len(response_call_ids)
            or any(not call_id for call_id in response_call_ids)
            or response_calls[0].tool_call_id != self.call.call_id
            or (decision_call_id and decision_call_id != self.call.call_id)
        ):
            raise ValueError("accepted tool exchange identities disagree")


@dataclass(frozen=True)
class PydanticAIGroundedDecisionPort:
    """Resolve one current call while retaining bounded official call/result history."""

    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_multimodal: bool
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    transport_timeout_s: float = 85.0
    policy_timeout_s: float | None = None
    provider_retry_backoff_s: float = _DEFAULT_PROVIDER_BACKOFF_S
    max_provider_retry_delay_s: float = _MAX_PROVIDER_BACKOFF_S
    envelope_binder: CanonicalProviderEnvelopeBinder = field(default_factory=CanonicalProviderEnvelopeBinder)
    reasoning_policy: ActionPolicyReasoningPolicy = field(default_factory=ActionPolicyReasoningPolicy)
    history_compaction_timeout_s: float = 10.0
    consumed_recovery_events: frozenset[str] = field(default_factory=frozenset, init=False, compare=False)
    last_call_profile: ActionPolicyCallProfile | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_catalog_specs: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_provider_retry_count: int = field(default=0, init=False, compare=False)
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(default=(), init=False, compare=False)
    last_request_breakdowns: tuple[ModelRequestBreakdown, ...] = field(default=(), init=False, compare=False)
    last_admitted_envelopes: tuple[CanonicalProviderEnvelope, ...] = field(default=(), init=False, compare=False)
    envelope_history: tuple[CanonicalProviderEnvelope, ...] = field(default=(), init=False, compare=False)
    last_local_failure: Mapping[str, object] = field(default_factory=dict, init=False, compare=False)
    last_tool_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_tool_resolution_detail: str = field(default="", init=False, compare=False)
    last_multiple_tool_call_attempt_count: int = field(default=0, init=False, compare=False)
    last_discarded_protocol_call_count: int = field(default=0, init=False, compare=False)
    last_history_compaction_count: int = field(default=0, init=False, compare=False)
    last_invocation_result: ModelInvocationResult[ResolvedModelDecision] | None = field(
        default=None, init=False, compare=False
    )
    message_history: tuple[object, ...] = field(default=(), init=False, compare=False, repr=False)
    active_task_identity: tuple[str, int] | None = field(default=None, init=False, compare=False, repr=False)
    last_history_compaction_status: str = field(default="not_triggered", init=False, compare=False)
    last_history_compaction_error: str = field(default="", init=False, compare=False)
    last_model_delivery: ModelTurnDelivery | None = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip() or not self.endpoint_host.strip():
            raise ValueError("PydanticAI model identity is required")
        if not 0 < self.transport_timeout_s <= 300:
            raise ValueError("PydanticAI transport timeout must be in (0, 300]")
        if self.policy_timeout_s is not None and not 1 < self.policy_timeout_s <= 300:
            raise ValueError("PydanticAI policy timeout must be in (1, 300]")
        if not 0 <= self.provider_retry_backoff_s <= self.max_provider_retry_delay_s:
            raise ValueError("provider retry backoff must fit its bounded delay")
        if not 0 < self.max_provider_retry_delay_s <= _MAX_PROVIDER_BACKOFF_S:
            raise ValueError("provider retry delay must be in (0, 5]")
        if not 0 < self.history_compaction_timeout_s <= 60:
            raise ValueError("history compaction timeout must be in (0, 60]")
        object.__setattr__(self, "perception_profile", DecisionPerceptionProfile(self.perception_profile))

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return GROUNDED_ACTION_DECISION_CAPABILITIES

    @property
    def compatibility_key(self) -> str:
        return ":".join(
            (
                GROUNDED_TOOLS_PROTOCOL,
                "pydantic-ai",
                self.provider_id,
                self.model_id,
                self.endpoint_host,
                self.perception_profile.value,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        semantic_started = time.perf_counter()
        provider_deadline_s = (
            semantic_started + self.policy_timeout_s - _POLICY_DEADLINE_SAFETY_S
            if self.policy_timeout_s is not None
            else None
        )
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_catalog_specs", ())
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_model_call_count", 0)
        object.__setattr__(self, "last_provider_retry_count", 0)
        object.__setattr__(self, "last_generation_attempts", ())
        object.__setattr__(self, "last_request_breakdowns", ())
        object.__setattr__(self, "last_admitted_envelopes", ())
        object.__setattr__(self, "last_local_failure", {})
        object.__setattr__(self, "last_discarded_protocol_call_count", 0)
        object.__setattr__(self, "last_history_compaction_count", 0)
        object.__setattr__(self, "last_history_compaction_status", "not_triggered")
        object.__setattr__(self, "last_history_compaction_error", "")
        object.__setattr__(self, "last_invocation_result", None)
        object.__setattr__(self, "last_model_delivery", None)
        task_identity = (
            request.agent_context.task.task_id,
            request.agent_context.goal_plan.task_revision,
        )
        previous_task_identity = self.active_task_identity
        if previous_task_identity is not None and previous_task_identity[0] != task_identity[0]:
            object.__setattr__(self, "message_history", ())
        object.__setattr__(self, "active_task_identity", task_identity)
        call_profile = self.reasoning_policy.select(
            request.agent_context,
            self.consumed_recovery_events,
        )
        object.__setattr__(self, "last_call_profile", call_profile)
        if call_profile.recovery_event_signature:
            object.__setattr__(
                self,
                "consumed_recovery_events",
                self.consumed_recovery_events | frozenset((call_profile.recovery_event_signature,)),
            )
        try:
            from pydantic_ai import (
                Agent,
                BinaryContent,
                DeferredToolRequests,
                DeferredToolResults,
                ExternalToolset,
                ModelRetry,
                ToolDefinition,
                ToolReturn,
                capture_run_messages,
            )
            from pydantic_ai.exceptions import (
                ModelAPIError,
                ToolFailed,
                UnexpectedModelBehavior,
                UsageLimitExceeded,
            )
            from pydantic_ai.usage import RunUsage, UsageLimits
        except ImportError:
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.INTERNAL_ERROR,
                    "PydanticAI optional dependency is not installed",
                ),
                request,
            )

        async def run_policy_envelope(
            current_envelope: CanonicalProviderEnvelope,
            *,
            agent_name: str,
            phase: str,
        ):
            # One semantic envelope owns one transport-retry allowance.  The
            # output fallback below is a second physical request for that same
            # envelope, not a new opportunity to reset network recovery.
            transport_retries_remaining = _MAX_PROVIDER_RETRIES
            pending_delivery_capture: tuple[object, ...] = ()
            (
                current_instructions,
                current_prompt,
                current_toolset,
                current_history,
                current_deferred_results,
            ) = _pydantic_model_boundary_codec(
                current_envelope,
                BinaryContent,
                DeferredToolResults,
                ExternalToolset,
                ToolFailed,
                ToolReturn,
                ToolDefinition,
            )

            def close_dispatched_pending_history() -> None:
                if not pending_call_parts or not pending_delivery_capture:
                    return
                object.__setattr__(
                    self,
                    "message_history",
                    _closed_history_after_failed_output(
                        tuple(current_history),
                        pending_delivery_capture,
                        pending_call_parts,
                    ),
                )

            async def run_output_sequence(
                *,
                force_required_action: bool,
                attempt_phase: str,
                output_retry_budget: int,
            ):
                nonlocal transport_retries_remaining
                current_agent = Agent(
                    self.model,
                    name=agent_name,
                    instructions=current_instructions,
                    output_type=[str, DeferredToolRequests],
                    retries={"tools": 0, "output": output_retry_budget},
                )

                @current_agent.output_validator
                def require_action_policy_tool_call(output: str | DeferredToolRequests):
                    if isinstance(output, str):
                        raise ModelRetry("Return one offered tool call for the current World; text-only output is invalid.")
                    return output

                def action_policy_model_settings(context):
                    # The first physical request preserves the selected reasoning
                    # profile.  PydanticAI's ordinary output retry and the explicit
                    # length fallback below both use the same provider-compatible
                    # final-action profile.
                    return _action_policy_physical_settings(
                        current_envelope,
                        require_action=force_required_action or bool(context.retry),
                    )

                physical_settings = _action_policy_physical_settings(
                    current_envelope,
                    require_action=force_required_action,
                )
                started = time.perf_counter()
                provider_retries_before = self.last_provider_retry_count
                captured_messages: tuple[object, ...] = ()

                async def invoke_current_agent():
                    nonlocal captured_messages, pending_delivery_capture
                    # PydanticAI captures only the first Agent.run in one
                    # capture context.  Transport recovery invokes Agent.run
                    # again, so each physical SDK run needs its own context and
                    # the latest run is the authoritative output-classification
                    # source.
                    with capture_run_messages() as current_messages:
                        try:
                            return await current_agent.run(
                                current_prompt,
                                toolsets=[current_toolset],
                                usage=RunUsage(),
                                usage_limits=UsageLimits(request_limit=output_retry_budget + 1),
                                model_settings=action_policy_model_settings,
                                message_history=current_history,
                                deferred_tool_results=current_deferred_results,
                            )
                        finally:
                            captured_messages = tuple(current_messages)
                            if captured_messages:
                                pending_delivery_capture = captured_messages

                try:
                    result = await self._run_provider_call(
                        invoke_current_agent,
                        phase=attempt_phase,
                        envelope=current_envelope,
                        provider_error_type=ModelAPIError,
                        physical_settings=physical_settings,
                        provider_retry_budget=transport_retries_remaining,
                    )
                    return result, None, (), False
                except UnexpectedModelBehavior as error:
                    serialized = _serialized_current_pydantic_invocation(
                        captured_messages,
                        max_response_count=output_retry_budget + 1,
                    )
                    response_count, failure_kind = _captured_output_failure(serialized)
                    can_retry_length = (
                        not force_required_action
                        and phase != ActionPolicyInvocationPhase.REPRESENTATION_REPAIR.value
                        and response_count == 1
                        and failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED
                    )
                    physical_attempt_phase = (
                        self.last_generation_attempts[-1].phase
                        if self.last_generation_attempts
                        and self.last_generation_attempts[-1].status == "started"
                        else attempt_phase
                    )
                    self._record_output_validation_exchanges(
                        serialized,
                        physical_attempt_phase,
                        current_envelope,
                        accepted=False,
                        terminal_failure=not can_retry_length,
                        physical_settings=physical_settings,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                    return None, error, captured_messages, can_retry_length
                finally:
                    transport_retries_remaining = max(
                        0,
                        transport_retries_remaining
                        - (self.last_provider_retry_count - provider_retries_before),
                    )

            output_retry_budget = 0 if phase == ActionPolicyInvocationPhase.REPRESENTATION_REPAIR.value else 1
            try:
                result, error, captured, can_retry_length = await run_output_sequence(
                    force_required_action=False,
                    attempt_phase=phase,
                    output_retry_budget=output_retry_budget,
                )
            except (asyncio.CancelledError, Exception):
                close_dispatched_pending_history()
                raise
            if result is not None:
                return result
            if can_retry_length:
                try:
                    result, error, captured, _unused = await run_output_sequence(
                        force_required_action=True,
                        attempt_phase=f"{phase}_output_retry",
                        output_retry_budget=0,
                    )
                except (asyncio.CancelledError, Exception):
                    close_dispatched_pending_history()
                    raise
                if result is not None:
                    return result
            if pending_call_parts:
                object.__setattr__(
                    self,
                    "message_history",
                    _closed_history_after_failed_output(
                        tuple(current_history),
                        captured,
                        pending_call_parts,
                    ),
                )
            assert error is not None
            raise error

        delivery: ModelTurnDelivery | None = None
        catalog: GroundedToolCatalog | None = None
        admitted: AdmittedProviderEnvelope | None = None
        envelope: CanonicalProviderEnvelope | None = None
        object.__setattr__(self, "last_tool_resolution_code", None)
        object.__setattr__(self, "last_tool_resolution_detail", "")
        object.__setattr__(self, "last_multiple_tool_call_attempt_count", 0)
        history_messages = self.message_history
        if history_messages:
            history_messages = _normalize_pydantic_history_for_current_task(
                history_messages,
                task_plan=self.envelope_binder.context_binder.public_task_plan(request.agent_context),
            )
        pending_call_parts: tuple[object, ...] = ()
        pending_call: ToolCall | None = None
        if history_messages:
            try:
                pending_call_parts = _pending_tool_parts_from_history(history_messages)
                pending_call = _pending_call_from_history(history_messages)
            except (TypeError, ValueError):
                return self._invocation_failure(
                    _failure(ModelFailureKind.INTERNAL_ERROR, "model_message_history_unavailable"),
                    request,
                )
            last_step = request.last_step
            if pending_call is not None and (
                last_step is None
                or str(getattr(getattr(last_step, "decision", None), "tool_call_id", "")) != pending_call.call_id
            ):
                return self._invocation_failure(
                    _failure(ModelFailureKind.INTERNAL_ERROR, "pending_tool_result_unavailable"),
                    request,
                )
        identity = CanonicalProviderIdentity(
            self.provider_id,
            self.model_id,
            self.endpoint_host,
            self.perception_profile.value,
        )

        def pack_history(
            messages: tuple[object, ...],
            *,
            request_timeout_s: float,
        ):
            return TurnPacker().pack(
                request,
                binder=self.envelope_binder,
                identity=identity,
                call_profile=call_profile,
                supports_multimodal=self.supports_multimodal,
                perception_profile=self.perception_profile,
                request_timeout_s=request_timeout_s,
                history_messages=messages,
                pending_tool_call_id=pending_call.call_id if pending_call is not None else "",
                pending_tool_name=pending_call.name if pending_call is not None else "",
            )

        try:
            before_compaction = history_messages
            initial_request_timeout_s = _remaining_action_attempt_timeout(
                deadline_s=provider_deadline_s,
                now_s=time.perf_counter(),
                retry_delay_reserve_s=self.max_provider_retry_delay_s,
                maximum_timeout_s=self.transport_timeout_s,
            )
            raw_packed = None
            try:
                raw_packed = pack_history(
                    history_messages,
                    request_timeout_s=initial_request_timeout_s,
                )
                raw_breakdown = raw_packed.admitted_envelope.token_breakdown
            except ModelRequestCapacityError as raw_capacity:
                raw_breakdown = raw_capacity.breakdown
            recent_exact_tokens = max(
                1,
                int(_available_history_tokens(raw_breakdown) * _HISTORY_RECENT_EXACT_TOKENS_RATIO),
            )
            projected_history = _project_expired_history(
                history_messages,
                max_estimated_tokens=recent_exact_tokens,
                current_world_observation_id=request.agent_context.current_observation.observation_id,
            )
            if projected_history != history_messages:
                history_messages = projected_history
                raw_packed = None
                try:
                    raw_packed = pack_history(
                        history_messages,
                        request_timeout_s=initial_request_timeout_s,
                    )
                    raw_breakdown = raw_packed.admitted_envelope.token_breakdown
                except ModelRequestCapacityError as projected_capacity:
                    raw_breakdown = projected_capacity.breakdown
            request_pressure = _history_compaction_required(
                raw_breakdown,
                has_history=bool(history_messages),
            )
            history_pressure = _history_economy_compaction_required(
                history_messages,
                max_estimated_tokens=recent_exact_tokens,
                available_history_tokens=_available_history_tokens(raw_breakdown),
                observed_history_tokens=raw_breakdown.history_tokens,
            )
            compaction_trigger = (
                "token_pressure" if request_pressure else "history_pressure" if history_pressure else ""
            )
            compaction_required = bool(compaction_trigger)
            if compaction_required:
                compaction_run = await _compact_pydantic_history(
                    history_messages,
                    model=self.model,
                    max_estimated_tokens=_available_history_tokens(raw_breakdown),
                    observed_estimated_tokens=raw_breakdown.history_tokens,
                    timeout_s=self.history_compaction_timeout_s,
                    trigger=compaction_trigger,
                )
            else:
                compaction_run = _HistoryCompactionRun(history_messages)
            history_messages = compaction_run.messages
            self._record_history_compaction_run(compaction_run)
            object.__setattr__(
                self,
                "last_history_compaction_count",
                max(
                    0,
                    _completed_exchange_count(before_compaction) - _completed_exchange_count(history_messages),
                ),
            )
            if compaction_required:
                request_timeout_s = _remaining_action_attempt_timeout(
                    deadline_s=provider_deadline_s,
                    now_s=time.perf_counter(),
                    retry_delay_reserve_s=self.max_provider_retry_delay_s,
                    maximum_timeout_s=self.transport_timeout_s,
                )
                packed = pack_history(
                    history_messages,
                    request_timeout_s=request_timeout_s,
                )
            elif raw_packed is not None:
                packed = raw_packed
            else:
                packed = pack_history(
                    history_messages,
                    request_timeout_s=initial_request_timeout_s,
                )
            delivery = packed.delivery
            catalog = packed.catalog
            admitted = packed.admitted_envelope
            envelope = admitted.envelope
            object.__setattr__(self, "last_catalog_count", len(catalog.specs))
            object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
            object.__setattr__(self, "last_catalog_specs", tuple(catalog.specs))
            object.__setattr__(self, "last_image_input_count", len(envelope.media))
            self._append_admitted_envelope(admitted)
            result = await run_policy_envelope(
                envelope,
                agent_name="action-policy",
                phase=call_profile.phase.value,
            )
            self._record_protocol_selection(result.output)
            resolution_error = None
            source_response = _latest_model_response(result)
            accepted_exchange, resolution_error, initial_calls = _resolve_deferred(
                result.output,
                catalog,
                request.context_id,
                source_response=source_response,
            )
            if accepted_exchange is None:
                accepted_exchange = _grounded_rejection_exchange(
                    result.output,
                    resolution_error,
                    initial_calls,
                    request.agent_context,
                    catalog.manifest,
                    source_response=source_response,
                )
            if accepted_exchange is not None:
                accepted_exchange = _reject_prohibited_recovery_replay(
                    accepted_exchange,
                    request.agent_context,
                )
            self._set_tool_resolution(resolution_error, accepted=accepted_exchange is not None)
            if accepted_exchange is None and initial_calls:
                repair_profile = self.reasoning_policy.repair()
                repair_prompt = _representation_repair_prompt(initial_calls, resolution_error, catalog.specs)
                repair_envelope = self.envelope_binder.bind_representation_repair(
                    envelope,
                    user_text=repair_prompt,
                    call_profile=repair_profile,
                    output_token_reserve=(
                        repair_profile.max_output_tokens
                        + self.envelope_binder.request_budget.protocol_reserve_tokens
                        + self.envelope_binder.request_budget.safety_margin_tokens
                    ),
                    request_timeout_s=_remaining_action_attempt_timeout(
                        deadline_s=provider_deadline_s,
                        now_s=time.perf_counter(),
                        retry_delay_reserve_s=self.max_provider_retry_delay_s,
                        maximum_timeout_s=self.transport_timeout_s,
                    ),
                )
                repair_budget = replace(
                    self.envelope_binder.request_budget,
                    max_output_tokens=repair_profile.max_output_tokens,
                )
                repair_admission = RequestAdmission().admit(repair_envelope, budget=repair_budget)
                if isinstance(repair_admission, RejectedProviderEnvelope):
                    raise ModelRequestCapacityError(repair_admission.token_breakdown)
                if isinstance(repair_admission, InvalidProviderEnvelope):
                    raise ValueError(f"{repair_admission.reason}: {repair_admission.detail}")
                self._append_admitted_envelope(repair_admission)
                repair_result = await run_policy_envelope(
                    repair_envelope,
                    agent_name="action-policy-representation-repair",
                    phase=repair_profile.phase.value,
                )
                self._record_protocol_selection(repair_result.output)
                repair_exchange, repair_error, _repaired_calls = _resolve_deferred(
                    repair_result.output,
                    catalog,
                    request.context_id,
                    source_response=_latest_model_response(repair_result),
                )
                if repair_exchange is not None and (
                    not _repair_preserves_rejected_semantics(
                        resolution_error,
                        initial_calls,
                        repair_exchange.call,
                        catalog.specs,
                    )
                ):
                    repair_exchange = None
                    repair_error = GroundedToolResolutionError(
                        GroundedToolResolutionCode.INVALID_ARGUMENTS,
                        "representation repair changed operation or semantic operands",
                    )
                resolution_error = repair_error
                self._set_tool_resolution(repair_error, accepted=repair_exchange is not None)
                if repair_exchange is not None:
                    accepted_exchange = repair_exchange
            if accepted_exchange is None:
                return self._invocation_failure(
                    _tool_resolution_failure(resolution_error),
                    request,
                    delivery,
                )
        except asyncio.CancelledError:
            self._invocation_failure(
                _failure(ModelFailureKind.TIMEOUT, "model invocation was cancelled"),
                request,
                delivery,
            )
            raise
        except UsageLimitExceeded:
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.PROVIDER_UNAVAILABLE,
                    "provider_request_limit_exhausted",
                    retryable=True,
                ),
                request,
                delivery,
            )
        except UnexpectedModelBehavior as error:
            self._record_local_failure(
                error,
                "pydantic_ai_output_validation",
                catalog.specs if catalog is not None else (),
            )
            failure_kind = _latest_structured_output_failure(self.last_generation_attempts)
            if failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED:
                failure = _failure(
                    ModelFailureKind.INVALID_RESPONSE,
                    "output_budget_exhausted",
                )
            elif failure_kind is StructuredOutputFailureKind.NO_TOOL_CALL:
                failure = _failure(
                    ModelFailureKind.INVALID_RESPONSE,
                    "no_tool_call",
                )
            else:
                failure = _failure(ModelFailureKind.SCHEMA_ERROR, "provider_envelope_invalid")
            return self._invocation_failure(
                failure,
                request,
                delivery,
            )
        except _ProviderCallExhausted as error:
            detail = error.detail
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.PROVIDER_UNAVAILABLE,
                    detail.reason,
                    retryable=detail.retryable,
                    provider_code=detail.code,
                    retry_after_s=detail.retry_after_s,
                ),
                request,
                delivery,
            )
        except ModelRequestCapacityError as error:
            self._append_request_breakdown(error.breakdown)
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.CONTEXT_CAPACITY,
                    "context_capacity",
                    attempt_origin=ProviderAttemptOrigin.LOCAL_RUNTIME,
                ),
                request,
                delivery,
            )
        except GroundedToolResolutionError as exc:
            self._set_tool_resolution(exc, accepted=False)
            if exc.code is GroundedToolResolutionCode.CATALOG_INVALID:
                return self._invocation_failure(
                    _failure(
                        ModelFailureKind.SCHEMA_ERROR,
                        "grounded_tool_catalog_invalid",
                        attempt_origin=ProviderAttemptOrigin.LOCAL_RUNTIME,
                    ),
                    request,
                    delivery,
                )
            return self._invocation_failure(
                _tool_resolution_failure(exc),
                request,
                delivery,
            )
        except Exception as error:
            self._record_local_failure(
                error,
                "local_runtime",
                catalog.specs if catalog is not None else (),
            )
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.INTERNAL_ERROR,
                    "PydanticAI decision adapter failed locally",
                    attempt_origin=ProviderAttemptOrigin.LOCAL_RUNTIME,
                ),
                request,
                delivery,
            )

        invocation_prompt_tokens = sum(item.prompt_tokens for item in self.last_generation_attempts)
        invocation_completion_tokens = sum(item.completion_tokens for item in self.last_generation_attempts)
        rate_limit_retries = sum(
            1
            for item in self.last_generation_attempts
            if isinstance(item.transcript, dict)
            and item.transcript.get("error.code") == ProviderFailureCode.RATE_LIMITED.value
        )
        metadata = ModelMetadata(
            provider_id=self.provider_id,
            model_id=self.model_id,
            endpoint_class="openai-compatible",
            prompt_version=self.envelope_binder.context_binder.prompt_version(request.agent_context),
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            latency_ms=(time.perf_counter() - semantic_started) * 1000,
            prompt_tokens=invocation_prompt_tokens,
            completion_tokens=invocation_completion_tokens,
            total_tokens=invocation_prompt_tokens + invocation_completion_tokens,
            rate_limit_retry_count=rate_limit_retries,
            transient_retry_count=max(0, self.last_provider_retry_count - rate_limit_retries),
            grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
            perception_profile=self.perception_profile.value,
            endpoint_host=self.endpoint_host,
        )
        if accepted_exchange is None:
            return self._invocation_failure(
                _failure(ModelFailureKind.INTERNAL_ERROR, "accepted_call_identity_unavailable"),
                request,
                delivery,
            )
        decision = accepted_exchange.decision
        if str(getattr(decision, "tool_call_id", "")) and decision.kind is not DecisionKind.ABORT:
            object.__setattr__(
                self,
                "message_history",
                _accepted_message_history(
                    result,
                    history_messages,
                    accepted_exchange,
                    pending_call_parts,
                ),
            )
        else:
            # A terminal local decision consumes the final pending ToolReturn.
            # No provider exchange is pending in the next episode.
            object.__setattr__(self, "message_history", ())
        object.__setattr__(self, "last_model_delivery", delivery)
        invocation = ModelInvocationResult(
            output=ResolvedModelDecision(decision, metadata),
            metadata=metadata,
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _invocation_failure(
        self,
        failure: ModelFailure,
        request: ModelDecisionRequest,
        delivery=None,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _lineage(self, request: ModelDecisionRequest, delivery=None) -> Mapping[str, object]:
        lineage = {
            "role": "ActionPolicy",
            "adapter": "pydantic-ai",
            "request_id": request.request_id,
            "context_id": request.context_id,
        }
        if delivery is not None:
            lineage.update(
                {
                    "delivery_id": delivery.delivery_id,
                    "world_observation_id": request.agent_context.current_observation.observation_id,
                }
            )
        if self.last_admitted_envelopes:
            lineage["envelope_ids"] = tuple(item.envelope_id for item in self.last_admitted_envelopes)
        return lineage

    def _diagnostics(self) -> Mapping[str, object]:
        return {
            "interaction_protocol": GROUNDED_TOOLS_PROTOCOL,
            "tool_transport": "pydantic-ai",
            "tool_catalog_count": self.last_catalog_count,
            "tool_catalog_bytes": self.last_catalog_bytes,
            "tool_catalog_specs": self.last_catalog_specs,
            "model_image_input_count": self.last_image_input_count,
            "policy_model_call_count": self.last_model_call_count,
            "provider_retry_count": self.last_provider_retry_count,
            "provider_envelope_ids": tuple(item.envelope_id for item in self.last_admitted_envelopes),
            "pre_provider_failure": self.last_local_failure,
            "tool_resolution_code": (
                self.last_tool_resolution_code.value if self.last_tool_resolution_code is not None else ""
            ),
            "tool_resolution_detail": self.last_tool_resolution_detail,
            "multiple_tool_call_attempt_count": self.last_multiple_tool_call_attempt_count,
            "discarded_protocol_call_count": self.last_discarded_protocol_call_count,
            "history_compaction_count": self.last_history_compaction_count,
            "history_compaction_status": self.last_history_compaction_status,
            "history_compaction_error": self.last_history_compaction_error,
            "reasoning_phase": (self.last_call_profile.phase.value if self.last_call_profile else ""),
            "reasoning_trigger": (self.last_call_profile.trigger.value if self.last_call_profile else ""),
            **request_breakdown_diagnostics(
                self.last_request_breakdowns,
                provider_reported_prompt_tokens=sum(item.prompt_tokens for item in self.last_generation_attempts),
            ),
        }

    def _append_request_breakdown(self, breakdown: ModelRequestBreakdown) -> None:
        object.__setattr__(self, "last_request_breakdowns", (*self.last_request_breakdowns, breakdown))

    def _append_admitted_envelope(self, admitted: AdmittedProviderEnvelope) -> None:
        self._append_request_breakdown(admitted.token_breakdown)
        object.__setattr__(
            self,
            "last_admitted_envelopes",
            (*self.last_admitted_envelopes, admitted.envelope),
        )
        object.__setattr__(self, "envelope_history", (*self.envelope_history, admitted.envelope)[-64:])

    def _set_tool_resolution(self, error: GroundedToolResolutionError | None, *, accepted: bool) -> None:
        if accepted:
            object.__setattr__(self, "last_tool_resolution_code", GroundedToolResolutionCode.ACCEPTED)
            object.__setattr__(self, "last_tool_resolution_detail", "")
            return
        if error is None:
            return
        object.__setattr__(self, "last_tool_resolution_code", error.code)
        object.__setattr__(self, "last_tool_resolution_detail", error.detail)

    def _record_protocol_selection(self, output: object) -> None:
        """Count provider batches that the one-step boundary serializes."""

        from pydantic_ai import DeferredToolRequests

        if not isinstance(output, DeferredToolRequests):
            return
        discarded = max(0, len(output.calls) - 1)
        if discarded == 0:
            return
        object.__setattr__(
            self,
            "last_multiple_tool_call_attempt_count",
            self.last_multiple_tool_call_attempt_count + 1,
        )
        object.__setattr__(
            self,
            "last_discarded_protocol_call_count",
            self.last_discarded_protocol_call_count + discarded,
        )

    def _record_history_compaction_run(self, run: _HistoryCompactionRun) -> None:
        """Record the Harness-owned summary call without making it task state."""

        from pydantic_ai.messages import ModelRequest, ModelResponse

        if not run.attempted:
            return
        object.__setattr__(
            self,
            "last_history_compaction_status",
            "failed" if run.error else "summarized",
        )
        object.__setattr__(self, "last_history_compaction_error", run.error)
        responses = tuple(
            (index, message) for index, message in enumerate(run.transcript) if isinstance(message, ModelResponse)
        )
        if not responses:
            attempt = ModelGenerationAttempt(
                attempt=len(self.last_generation_attempts) + 1,
                phase=f"history_compaction:{run.trigger}",
                schema_name=_HISTORY_COMPACTION_SCHEMA,
                status="failed",
                latency_ms=run.latency_ms,
                exception_class=run.error.split(":", 1)[0],
                role="history_compactor",
                mode="semantic_compaction",
                schema_version=_HISTORY_COMPACTION_SCHEMA,
                trigger=run.trigger,
                transcript={
                    "openinference.span.kind": "LLM",
                    "llm.system": self.provider_id,
                    "llm.model_name": self.model_id,
                    "llm.input_messages": to_json_compatible(run.transcript),
                    "llm.output_messages": [],
                    "status": "failed",
                    "error": run.error,
                },
            )
            object.__setattr__(
                self,
                "last_generation_attempts",
                (*self.last_generation_attempts, attempt),
            )
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            return
        for response_index, response in responses:
            request = next(
                (message for message in reversed(run.transcript[:response_index]) if isinstance(message, ModelRequest)),
                None,
            )
            usage = response.usage
            prompt_tokens = int(getattr(usage, "input_tokens", 0))
            completion_tokens = int(getattr(usage, "output_tokens", 0))
            accepted = not run.error and response_index == responses[-1][0]
            attempt = ModelGenerationAttempt(
                attempt=len(self.last_generation_attempts) + 1,
                phase=f"history_compaction:{run.trigger}",
                schema_name=_HISTORY_COMPACTION_SCHEMA,
                status="accepted" if accepted else "failed",
                response_id=str(response.provider_response_id or ""),
                latency_ms=run.latency_ms if accepted else 0.0,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                finish_reason=str(response.finish_reason or "")[:80],
                final_content_present=accepted,
                role="history_compactor",
                mode="semantic_compaction",
                schema_version=_HISTORY_COMPACTION_SCHEMA,
                trigger=run.trigger,
                transcript={
                    "openinference.span.kind": "LLM",
                    "llm.system": self.provider_id,
                    "llm.model_name": self.model_id,
                    "llm.input_messages": to_json_compatible(request) if request else None,
                    "llm.output_messages": to_json_compatible(response),
                    "status": "accepted" if accepted else "failed",
                    "error": run.error,
                },
            )
            object.__setattr__(
                self,
                "last_generation_attempts",
                (*self.last_generation_attempts, attempt),
            )
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)

    async def _run_provider_call(
        self,
        call,
        *,
        phase: str,
        envelope: CanonicalProviderEnvelope,
        provider_error_type: type[Exception],
        physical_settings: Mapping[str, object] | None = None,
        provider_retry_budget: int = _MAX_PROVIDER_RETRIES,
    ) -> object:
        if not 0 <= provider_retry_budget <= _MAX_PROVIDER_RETRIES:
            raise ValueError("provider retry budget is outside the supported logical-turn bound")
        for retry_index in range(provider_retry_budget + 1):
            attempt_phase = phase if retry_index == 0 else f"{phase}_provider_retry"
            if retry_index:
                object.__setattr__(
                    self,
                    "last_provider_retry_count",
                    self.last_provider_retry_count + 1,
                )
            started = time.perf_counter()
            self._record_attempt_started(envelope, attempt_phase, physical_settings=physical_settings)
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            try:
                result = await call()
            except asyncio.CancelledError:
                self._record_cancelled_attempt(
                    attempt_phase,
                    envelope,
                    physical_settings=physical_settings,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                raise
            except provider_error_type as error:
                detail = _classify_provider_failure(error)
                self._record_provider_failure(
                    detail,
                    attempt_phase,
                    envelope,
                    physical_settings=physical_settings,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                if retry_index >= provider_retry_budget or not detail.retryable:
                    raise _ProviderCallExhausted(detail) from error
                delay_s = min(
                    detail.retry_after_s
                    if detail.retry_after_s is not None
                    else self.provider_retry_backoff_s * (2**retry_index),
                    self.max_provider_retry_delay_s,
                )
                if delay_s:
                    await asyncio.sleep(delay_s)
                continue
            self._record_generation(
                result,
                attempt_phase,
                envelope,
                physical_settings=physical_settings,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            return result
        raise AssertionError("bounded provider retry loop did not resolve")

    def _record_attempt_started(
        self,
        envelope: CanonicalProviderEnvelope,
        phase: str,
        *,
        physical_settings: Mapping[str, object] | None = None,
    ) -> None:
        actual_settings = dict(physical_settings or envelope.model_settings)
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "canonical_provider_envelope": envelope.model_boundary_projection(),
            "envelope_id": envelope.envelope_id,
            "llm.model_settings": to_json_compatible(actual_settings),
            "status": "started",
            "network_dispatched": False,
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="started",
            envelope_id=envelope.envelope_id,
            envelope_projection=envelope.model_boundary_projection(),
            **self._attempt_role_fields(envelope, physical_settings=actual_settings),
            transcript=transcript,
        )
        object.__setattr__(self, "last_generation_attempts", (*self.last_generation_attempts, attempt))

    def _record_generation(
        self,
        result: object,
        phase: str,
        envelope: CanonicalProviderEnvelope,
        *,
        physical_settings: Mapping[str, object] | None = None,
        latency_ms: float = 0.0,
    ) -> None:
        actual_settings = dict(physical_settings or envelope.model_settings)
        messages = json.loads(result.new_messages_json())
        requests = [message for message in messages if message.get("kind") == "request"]
        responses = [message for message in messages if message.get("kind") == "response"]
        if len(responses) > 1:
            self._record_output_validation_exchanges(
                messages,
                phase,
                envelope,
                accepted=True,
                physical_settings=actual_settings,
                latency_ms=latency_ms,
            )
            return
        usage = result.usage
        response = responses[-1] if responses else {}
        attempt_prompt_tokens, raw_cumulative_prompt_tokens = _attempt_token_delta(
            self.last_generation_attempts,
            response,
            usage,
            "input_tokens",
        )
        attempt_completion_tokens, raw_cumulative_completion_tokens = _attempt_token_delta(
            self.last_generation_attempts,
            response,
            usage,
            "output_tokens",
        )
        attempt_cached_input_tokens = _response_usage_int(response, "cache_read_tokens")
        reasoning_content_present, reasoning_tokens = _response_reasoning_observation(response)
        final_content_tokens = max(0, attempt_completion_tokens - reasoning_tokens)
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": envelope.model_boundary_projection()["messages"],
            "llm.actual_messages": requests,
            "llm.output_messages": responses,
            "llm.tools": [
                {
                    "tool.name": getattr(spec, "name", ""),
                    "tool.description": getattr(spec, "description", ""),
                    "tool.json_schema": to_json_compatible(spec.parameters_json_schema),
                }
                for spec in envelope.function_tools
            ],
            "llm.model_settings": to_json_compatible(actual_settings),
            "llm.token_count.prompt": attempt_prompt_tokens,
            "llm.token_count.completion": attempt_completion_tokens,
            "llm.token_count.total": attempt_prompt_tokens + attempt_completion_tokens,
            "llm.token_count.reasoning": reasoning_tokens,
            "llm.token_count.final_content": final_content_tokens,
            "llm.output.reasoning_content_present": reasoning_content_present,
            "estimated_request_tokens": 0,
            "attempt_input_tokens": attempt_prompt_tokens,
            "attempt_cached_input_tokens": attempt_cached_input_tokens,
            "provider_raw_cumulative_input_tokens": raw_cumulative_prompt_tokens,
            "provider_raw_cumulative_output_tokens": raw_cumulative_completion_tokens,
            "response.id": str(response.get("provider_response_id") or ""),
            "status": "accepted",
            "error": "",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts),
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="accepted",
            response_id=str(response.get("provider_response_id") or ""),
            latency_ms=latency_ms,
            prompt_tokens=attempt_prompt_tokens,
            completion_tokens=attempt_completion_tokens,
            total_tokens=attempt_prompt_tokens + attempt_completion_tokens,
            finish_reason=str(response.get("finish_reason") or "")[:80],
            max_output_tokens=int(actual_settings.get("max_tokens", 0)),
            final_content_present=bool(getattr(result.output, "calls", ())),
            reasoning_content_present=reasoning_content_present,
            role="action_policy",
            mode="single_action",
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            thinking_requested=envelope.thinking_requested,
            thinking_effective=("enabled" if actual_settings.get("thinking") is True else "disabled"),
            trigger=envelope.attempt_trigger,
            reasoning_tokens=reasoning_tokens,
            final_content_tokens=final_content_tokens,
            final_tool_call_present=bool(getattr(result.output, "calls", ())),
            envelope_id=envelope.envelope_id,
            envelope_projection=envelope.model_boundary_projection(),
            transcript=transcript,
        )
        self._replace_active_attempt(attempt)

    def _record_output_validation_exchanges(
        self,
        messages: list[dict[str, object]],
        phase: str,
        envelope: CanonicalProviderEnvelope,
        *,
        accepted: bool,
        terminal_failure: bool = True,
        physical_settings: Mapping[str, object] | None = None,
        latency_ms: float,
    ) -> None:
        """Record each physical SDK output-validation exchange exactly once."""

        if not self.last_generation_attempts or self.last_generation_attempts[-1].status != "started":
            raise RuntimeError("PydanticAI output retry has no active provider attempt")
        response_rows = tuple(
            (index, message) for index, message in enumerate(messages) if message.get("kind") == "response"
        )
        if not response_rows:
            return
        prefix = self.last_generation_attempts[:-1]
        cumulative_prompt_tokens = 0
        cumulative_completion_tokens = 0
        attempts: list[ModelGenerationAttempt] = []
        tools = _tool_transcript(envelope.function_tools)
        for ordinal, (response_index, response) in enumerate(response_rows):
            is_final = ordinal == len(response_rows) - 1
            prompt_tokens = max(0, _response_usage_int(response, "input_tokens"))
            completion_tokens = max(0, _response_usage_int(response, "output_tokens"))
            reasoning_content_present, reasoning_tokens = _response_reasoning_observation(response)
            final_content_tokens = max(0, completion_tokens - reasoning_tokens)
            cumulative_prompt_tokens += prompt_tokens
            cumulative_completion_tokens += completion_tokens
            parts = response.get("parts")
            parts = parts if isinstance(parts, list) else []
            has_tool_call = any(isinstance(part, Mapping) and part.get("part_kind") == "tool-call" for part in parts)
            has_text = any(
                isinstance(part, Mapping) and part.get("part_kind") == "text" and bool(part.get("content"))
                for part in parts
            )
            output_failure_kind = (
                None
                if accepted and is_final and has_tool_call
                else _structured_output_failure_for_response(response, has_tool_call=has_tool_call)
            )
            status = (
                "accepted"
                if accepted and is_final
                else "failed"
                if is_final and terminal_failure
                else "invalid"
            )
            response_settings = dict(physical_settings or envelope.model_settings)
            if ordinal:
                response_settings = _action_policy_physical_settings(envelope, require_action=True)
            transcript = {
                "openinference.span.kind": "LLM",
                "llm.system": self.provider_id,
                "llm.model_name": self.model_id,
                "llm.configured_endpoint_host": self.endpoint_host,
                "llm.input_messages": envelope.model_boundary_projection()["messages"],
                "llm.actual_messages": messages[:response_index],
                "llm.output_messages": [response],
                "llm.tools": tools,
                "llm.model_settings": to_json_compatible(response_settings),
                "llm.token_count.prompt": prompt_tokens,
                "llm.token_count.completion": completion_tokens,
                "llm.token_count.total": prompt_tokens + completion_tokens,
                "llm.token_count.reasoning": reasoning_tokens,
                "llm.token_count.final_content": final_content_tokens,
                "llm.output.reasoning_content_present": reasoning_content_present,
                "attempt_input_tokens": prompt_tokens,
                "attempt_cached_input_tokens": max(0, _response_usage_int(response, "cache_read_tokens")),
                "provider_raw_cumulative_input_tokens": cumulative_prompt_tokens,
                "provider_raw_cumulative_output_tokens": cumulative_completion_tokens,
                "response.id": str(response.get("provider_response_id") or ""),
                "status": status,
                "error.code": output_failure_kind.value if output_failure_kind else "",
            }
            attempts.append(
                ModelGenerationAttempt(
                    attempt=len(prefix) + ordinal + 1,
                    phase=phase if ordinal == 0 else f"{phase}_output_retry",
                    schema_name=GROUNDED_TOOLS_PROTOCOL,
                    status=status,
                    response_id=str(response.get("provider_response_id") or ""),
                    latency_ms=latency_ms if is_final else 0.0,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    output_failure_kind=output_failure_kind,
                    finish_reason=str(response.get("finish_reason") or "")[:80],
                    max_output_tokens=int(response_settings.get("max_tokens", 0)),
                    final_content_present=has_text or has_tool_call,
                    reasoning_content_present=reasoning_content_present,
                    role="action_policy",
                    mode="single_action",
                    schema_version=GROUNDED_TOOLS_PROTOCOL,
                    thinking_requested=envelope.thinking_requested,
                    thinking_effective=("enabled" if response_settings.get("thinking") is True else "disabled"),
                    trigger=envelope.attempt_trigger,
                    reasoning_tokens=reasoning_tokens,
                    final_content_tokens=final_content_tokens,
                    final_tool_call_present=has_tool_call,
                    envelope_id=envelope.envelope_id,
                    envelope_projection=envelope.model_boundary_projection(),
                    transcript=transcript,
                )
            )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*prefix, *attempts),
        )
        object.__setattr__(
            self,
            "last_model_call_count",
            self.last_model_call_count + max(0, len(response_rows) - 1),
        )

    def _record_cancelled_attempt(
        self,
        phase: str,
        envelope: CanonicalProviderEnvelope,
        *,
        physical_settings: Mapping[str, object] | None = None,
        latency_ms: float,
    ) -> None:
        actual_settings = dict(physical_settings or envelope.model_settings)
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": envelope.model_boundary_projection()["messages"],
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(envelope.function_tools),
            "llm.model_settings": to_json_compatible(actual_settings),
            "status": "cancelled",
            "network_dispatched": True,
            "error.code": "cancelled",
            "error.exception_class": "CancelledError",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts),
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="cancelled",
            latency_ms=latency_ms,
            exception_class="CancelledError",
            envelope_id=envelope.envelope_id,
            envelope_projection=envelope.model_boundary_projection(),
            **self._attempt_role_fields(envelope, physical_settings=actual_settings),
            transcript=transcript,
        )
        self._replace_active_attempt(attempt)

    def _record_provider_failure(
        self,
        detail: _ProviderFailureDetail,
        phase: str,
        envelope: CanonicalProviderEnvelope,
        *,
        physical_settings: Mapping[str, object] | None = None,
        latency_ms: float,
    ) -> None:
        actual_settings = dict(physical_settings or envelope.model_settings)
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": envelope.model_boundary_projection()["messages"],
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(envelope.function_tools),
            "llm.model_settings": to_json_compatible(actual_settings),
            "status": "failed",
            "error.code": detail.code.value,
            "error.reason": detail.reason,
            "error.exception_class": detail.exception_class,
            "error.http_status": detail.status_code,
            "error.retryable": detail.retryable,
            "error.retry_after_s": detail.retry_after_s,
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts),
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="failed",
            latency_ms=latency_ms,
            exception_class=detail.exception_class,
            envelope_id=envelope.envelope_id,
            envelope_projection=envelope.model_boundary_projection(),
            **self._attempt_role_fields(envelope, physical_settings=actual_settings),
            transcript=transcript,
        )
        self._replace_active_attempt(attempt)

    def _replace_active_attempt(self, attempt: ModelGenerationAttempt) -> None:
        if not self.last_generation_attempts or self.last_generation_attempts[-1].status != "started":
            raise RuntimeError("provider attempt completion has no recorded boundary input")
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts[:-1], attempt),
        )

    def _attempt_role_fields(
        self,
        envelope: CanonicalProviderEnvelope,
        *,
        physical_settings: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        actual_settings = dict(physical_settings or envelope.model_settings)
        return {
            "max_output_tokens": int(actual_settings.get("max_tokens", 0)),
            "role": "action_policy",
            "mode": "single_action",
            "schema_version": GROUNDED_TOOLS_PROTOCOL,
            "thinking_requested": envelope.thinking_requested,
            "thinking_effective": "enabled" if actual_settings.get("thinking") is True else "disabled",
            "trigger": envelope.attempt_trigger,
        }

    def _record_local_failure(
        self,
        error: Exception,
        phase: str,
        specs: tuple[object, ...],
    ) -> None:
        object.__setattr__(
            self,
            "last_local_failure",
            {
                "phase": phase,
                "exception_class": type(error).__name__,
                "detail": str(error)[:500] or "PydanticAI decision adapter failed locally",
                "constructed_tool_count": len(specs),
                "provider_attempts": self.last_model_call_count,
            },
        )


def openai_compatible_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Build native-tool policy transport for supported OpenAI-compatible profiles."""

    if not 1 < call_timeout_s <= 300:
        raise ValueError("PydanticAI policy timeout must be in (1, 300]")
    env = os.environ if environment is None else environment
    configured = pydantic_ai_model_from_environment(env, call_timeout_s=call_timeout_s)
    selected_perception = DecisionPerceptionProfile(
        perception_profile or env.get("LLM_DECISION_PERCEPTION", DecisionPerceptionProfile.TEXT_ONLY.value)
    )
    compaction_timeout_s, retry_delay_budget_s, transport_timeout_s = _provider_time_budgets(call_timeout_s)
    port = PydanticAIGroundedDecisionPort(
        model=configured.model,
        provider_id=configured.provider_id,
        model_id=configured.model_id,
        endpoint_host=configured.endpoint_host,
        supports_multimodal=configured.supports_multimodal,
        perception_profile=selected_perception,
        transport_timeout_s=transport_timeout_s,
        policy_timeout_s=call_timeout_s,
        provider_retry_backoff_s=min(_DEFAULT_PROVIDER_BACKOFF_S, retry_delay_budget_s),
        max_provider_retry_delay_s=retry_delay_budget_s,
        history_compaction_timeout_s=compaction_timeout_s,
        reasoning_policy=ActionPolicyReasoningPolicy(
            ordinary_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_ORDINARY_MAX_TOKENS",
                1024,
                512,
                1024,
            ),
            deliberate_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_DELIBERATE_MAX_TOKENS",
                2048,
                1024,
                2048,
            ),
            repair_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_REPRESENTATION_REPAIR_MAX_TOKENS",
                512,
                256,
                512,
            ),
        ),
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=call_timeout_s)


def pydantic_ai_model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
) -> ConfiguredPydanticAIModel:
    """Build the one supported PydanticAI provider model configuration."""

    try:
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.models.zai import ZaiModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.providers.zai import ZaiProvider
    except ImportError as exc:
        raise RuntimeError("install the pydantic-ai project extra") from exc
    env = os.environ if environment is None else environment
    profile = env.get("LLM_ACTIVE_PROFILE", "").strip().casefold()
    if profile not in {"zhipu", "aliyun", "deepseek", "mistral", "gemini", "local"}:
        raise ValueError("PydanticAI model adapter requires a supported OpenAI-compatible profile")
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("PydanticAI model adapter forbids provider fallback")
    prefix = {
        "zhipu": "LLM_ZHIPU",
        "aliyun": "LLM_ALIYUN",
        "deepseek": "LLM_DEEPSEEK",
        "mistral": "LLM_MISTRAL",
        "gemini": "LLM_GEMINI",
        "local": "LLM_LOCAL",
    }[profile]
    if (
        profile == "local"
        and env.get("LLM_LOCAL_PROVIDER", "openai_compatible").strip().casefold() != "openai_compatible"
    ):
        raise ValueError("local PydanticAI ActionPolicy requires LLM_LOCAL_PROVIDER=openai_compatible")
    base_url = (
        env.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1").strip()
        if profile == "local"
        else _required(env, f"{prefix}_BASE_URL")
    )
    model_id = (
        (env.get("LLM_LOCAL_MODEL_ID") or env.get("LLM_LOCAL_MODEL") or "qwen2.5:7b").strip()
        if profile == "local"
        else _required(env, f"{prefix}_MODEL")
    )
    compaction_timeout_s, _retry_delay_budget_s, transport_timeout_s = _provider_time_budgets(call_timeout_s)
    client = AsyncOpenAI(
        api_key=(env.get("LLM_LOCAL_API_KEY", "local") or "local")
        if profile == "local"
        else _required(env, f"{prefix}_API_KEY"),
        base_url=base_url,
        # Harness compaction reuses this model directly, while normal policy
        # requests carry their shorter role deadline in ModelSettings.timeout.
        timeout=max(compaction_timeout_s, transport_timeout_s),
        max_retries=0,
    )
    model_settings = {
        "max_tokens": _HISTORY_COMPACTION_MAX_OUTPUT_TOKENS,
        "temperature": 0.0,
        # Compaction and ordinary ActionPolicy calls default to non-thinking.
        # The canonical per-call envelope overrides this only for a deliberate
        # recovery invocation.
        "thinking": False,
    }
    if profile == "deepseek":
        model = OpenAIChatModel(
            model_id,
            provider=DeepSeekProvider(openai_client=client),
            # DeepSeek Chat Completions uses ``max_tokens``. PydanticAI's
            # OpenAI-compatible default otherwise maps the generic setting to
            # ``max_completion_tokens``, which this endpoint does not enforce.
            profile={
                "openai_chat_supports_max_completion_tokens": False,
                # DeepSeek V4 accepts ``required`` with tools in its supported
                # per-call thinking modes even though PydanticAI's conservative
                # provider profile disables it for every V4 model name.
                "openai_supports_tool_choice_required": True,
            },
            settings=model_settings,
        )
    elif profile in {"zhipu", "aliyun"}:
        model = ZaiModel(
            model_id,
            provider=ZaiProvider(openai_client=client),
            settings=model_settings,
        )
    else:
        model = OpenAIChatModel(
            model_id,
            provider=OpenAIProvider(openai_client=client),
            settings=model_settings,
        )
    return ConfiguredPydanticAIModel(
        model,
        profile,
        model_id,
        _endpoint_host(base_url),
        profile == "zhipu" and _zhipu_supports_multimodal(model_id),
    )


def _bounded_reasoning_tokens(
    environment: Mapping[str, str],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environment.get(key, "").strip()
    value = default if not raw else int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be within [{minimum}, {maximum}]")
    return value


def _provider_time_budgets(call_timeout_s: float) -> tuple[float, float, float]:
    """Set role caps whose actual use is bounded by one propagated deadline."""

    retry_delay_budget_s = min(_MAX_PROVIDER_BACKOFF_S, max(0.1, call_timeout_s * 0.1))
    callable_budget_s = call_timeout_s - retry_delay_budget_s - _POLICY_DEADLINE_SAFETY_S
    transport_timeout_s = callable_budget_s / 2
    compaction_timeout_s = min(60.0, max(0.25, transport_timeout_s))
    if transport_timeout_s <= 0:
        raise ValueError("PydanticAI policy timeout cannot fit compaction and provider recovery")
    return compaction_timeout_s, retry_delay_budget_s, transport_timeout_s


def _remaining_action_attempt_timeout(
    *,
    deadline_s: float | None,
    now_s: float,
    retry_delay_reserve_s: float,
    maximum_timeout_s: float,
) -> float:
    """Share the real remaining deadline across the two bounded provider attempts."""

    if deadline_s is None:
        return maximum_timeout_s
    remaining_callable_s = deadline_s - now_s - retry_delay_reserve_s
    timeout_s = min(maximum_timeout_s, remaining_callable_s / 2)
    if timeout_s <= 0:
        raise TimeoutError("provider deadline exhausted before ActionPolicy dispatch")
    return timeout_s


def zhipu_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Compatibility entry point for existing Zhipu/Aliyun callers."""

    return openai_compatible_pydantic_ai_policy_from_environment(
        environment,
        call_timeout_s=call_timeout_s,
        perception_profile=perception_profile,
    )


def _endpoint_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return (parsed.netloc or parsed.path.split("/", 1)[0]).strip().casefold()


def _resolve_deferred(
    output,
    catalog,
    context_id: str,
    *,
    source_response=None,
):
    from pydantic_ai import DeferredToolRequests

    if not isinstance(output, DeferredToolRequests) or output.approvals:
        return None, None, ()
    if not output.calls:
        return None, GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS), ()
    repair_anchor: tuple[ToolCall, GroundedToolResolutionError] | None = None
    # Provider calls are ordered proposals. This boundary owns conversion to
    # the Runtime's one-decision-per-fresh-World contract: only the first call
    # is eligible; later calls are neither fallbacks nor pending work.
    for call in tuple(output.calls)[:1]:
        try:
            arguments = call.args_as_dict(raise_if_invalid=True)
            parsed_call = ToolCall(call.tool_name, arguments, call.tool_call_id)
        except (ValueError, TypeError):
            continue
        reconciliation = ProviderCallNormalizer().normalize(
            parsed_call,
            catalog,
        )
        if reconciliation.status is not ToolCallReconciliationStatus.EXACT:
            error = _reconciliation_error(reconciliation)
            if error.code is not GroundedToolResolutionCode.UNKNOWN_OPERATION and repair_anchor is None:
                repair_anchor = (parsed_call, error)
            continue
        assert reconciliation.exact_call is not None
        try:
            resolution = resolve_grounded_action_call(
                catalog,
                reconciliation.exact_call,
                expected_context_id=context_id,
                expected_delivery_id=catalog.delivery_id,
                expected_catalog_id=catalog.catalog_id,
            )
        except GroundedToolResolutionError as exc:
            return None, exc, (reconciliation.exact_call,)
        except (ValueError, TypeError):
            return (
                None,
                GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS),
                (reconciliation.exact_call,),
            )
        accepted_call = reconciliation.exact_call
        return (
            AcceptedToolExchange(
                accepted_call,
                resolution.decision,
                _accepted_model_response(
                    source_response,
                    accepted_call,
                    proposed_calls=tuple(output.calls),
                    discarded_call_count=max(0, len(output.calls) - 1),
                ),
                max(0, len(output.calls) - 1),
            ),
            None,
            (),
        )
    if repair_anchor is not None:
        return None, repair_anchor[1], (repair_anchor[0],)
    return None, GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS), ()


def _grounded_rejection_exchange(
    output,
    error: GroundedToolResolutionError | None,
    calls: tuple[ToolCall, ...],
    context: AgentContext,
    manifest: DeliveryManifest,
    *,
    source_response,
) -> AcceptedToolExchange | None:
    """Close one parsed semantic rejection as its same-call ToolReturn.

    Representation failures still use the one bounded representation repair.
    A known, schema-valid operation applied to an unavailable current target is
    already semantically parsed, so asking the provider to rewrite its JSON
    would hide the real feedback and can repeat the same invalid operation.
    """

    from pydantic_ai import DeferredToolRequests

    if (
        error is None
        or error.code is not GroundedToolResolutionCode.GROUNDING_GAP
        or len(calls) != 1
        or not isinstance(output, DeferredToolRequests)
    ):
        return None
    call = calls[0]
    proposed_calls = tuple(output.calls)
    discarded_call_count = max(0, len(proposed_calls) - 1)
    return AcceptedToolExchange(
        call,
        grounded_tool_rejection_decision(
            error,
            call,
            context.context_id,
            context,
            manifest,
        ),
        _accepted_model_response(
            source_response,
            call,
            proposed_calls=proposed_calls,
            discarded_call_count=discarded_call_count,
        ),
        discarded_call_count,
    )


def _reject_prohibited_recovery_replay(
    accepted: AcceptedToolExchange,
    context: AgentContext,
) -> AcceptedToolExchange:
    """Return one typed zero-dispatch result for an exact advisory-recovery replay."""

    raw_signature = context.control_feedback.get("prohibited_attempt_signature")
    if not isinstance(raw_signature, Mapping):
        return accepted
    try:
        prohibited = PublicAttemptSignature(
            operation=str(raw_signature["operation"]),
            page_semantic_digest=str(raw_signature["page_semantic_digest"]),
            target_semantic_digest=str(raw_signature["target_semantic_digest"]),
            destination_semantic_digest=str(raw_signature["destination_semantic_digest"]),
            parameter_digest=str(raw_signature["parameter_digest"]),
        )
    except (KeyError, TypeError, ValueError):
        return accepted
    if context.current_observation is None:
        return accepted
    decision = accepted.decision
    if isinstance(decision, LocalToolResult):
        current = decision.rejected_attempt_signature or public_attempt_signature(
            decision.tool_name,
            "",
            "",
            decision.arguments,
            context.current_observation,
        )
    elif isinstance(decision, RequestActionPage):
        current = public_attempt_signature(
            "find_controls",
            "",
            "",
            {"query": decision.query},
            context.current_observation,
        )
    elif isinstance(decision, RequestObservation):
        current = public_attempt_signature(
            "request_observation",
            "",
            "",
            {
                "purpose": decision.purpose,
                "subject_id": decision.subject_id,
                "evidence_property": decision.evidence_property,
                "cursor": decision.cursor,
            },
            context.current_observation,
        )
    else:
        return accepted
    if current != prohibited:
        return accepted
    rejected = ToolRejectedResult(
        context.context_id,
        accepted.call.name,
        accepted.call.arguments,
        {
            "kind": "recovery_repeat_rejected",
            "failure_kind": "control_feedback_prohibited_attempt",
            "attempted_operation": accepted.call.name,
            "dispatch": "not_sent",
            "world_changed": False,
            "must_change": ("operation", "arguments"),
        },
        accepted.call.call_id,
        rejected_attempt_signature=current,
    )
    return replace(accepted, decision=rejected)


def _latest_model_response(result):
    """Return the current SDK response, excluding earlier supplied history."""

    from pydantic_ai.messages import ModelResponse

    responses = tuple(message for message in result.all_messages() if isinstance(message, ModelResponse))
    if not responses:
        raise ValueError("PydanticAI produced no model response")
    return responses[-1]


def _accepted_model_response(
    source_response,
    accepted_call: ToolCall,
    *,
    proposed_calls: tuple[object, ...] = (),
    discarded_call_count: int = 0,
):
    """Keep the exact accepted response, including provider reasoning metadata."""

    from pydantic_ai.messages import ModelResponse, ToolCallPart

    if source_response is not None and not isinstance(source_response, ModelResponse):
        raise TypeError("source response is not a PydanticAI ModelResponse")
    calls = tuple(proposed_calls)
    if not calls and source_response is not None:
        calls = tuple(part for part in source_response.parts if isinstance(part, ToolCallPart))
    if (
        len(calls) != discarded_call_count + 1
        or any(not isinstance(part, ToolCallPart) for part in calls)
        or calls[0].tool_call_id != accepted_call.call_id
        or len({part.tool_call_id for part in calls}) != len(calls)
    ):
        raise ValueError("accepted call proposals are incomplete or ambiguous")
    if source_response is None:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    accepted_call.name,
                    to_json_compatible(accepted_call.arguments),
                    accepted_call.call_id,
                ),
                *calls[1:],
            ]
        )
    source_calls = tuple(part for part in source_response.parts if isinstance(part, ToolCallPart))
    source_identities = tuple((part.tool_name, part.args_as_dict(), part.tool_call_id) for part in source_calls)
    proposed_identities = tuple((part.tool_name, part.args_as_dict(), part.tool_call_id) for part in calls)
    if source_identities != proposed_identities:
        raise ValueError("source response and deferred calls disagree")
    return source_response


def _closed_history_after_failed_output(
    prior_history: tuple[object, ...],
    captured: tuple[object, ...],
    pending_calls: tuple[object, ...],
) -> tuple[object, ...]:
    """Close the prior deferred exchange without retaining rejected model output."""

    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    current_run_id = next(
        (str(getattr(message, "run_id", "") or "") for message in reversed(captured) if getattr(message, "run_id", "")),
        "",
    )
    if not current_run_id:
        raise ValueError("captured PydanticAI invocation has no run identity")
    current_requests = tuple(
        message
        for message in captured
        if isinstance(message, ModelRequest) and str(getattr(message, "run_id", "") or "") == current_run_id
    )
    pending_identities = tuple((part.tool_name, part.tool_call_id) for part in pending_calls)
    closing_requests = tuple(
        message for message in current_requests if any(isinstance(part, ToolReturnPart) for part in message.parts)
    )
    returned_identities = tuple(
        (part.tool_name, part.tool_call_id)
        for message in closing_requests
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    if (
        len(closing_requests) != 1
        or len(returned_identities) != len(pending_identities)
        or len(set(returned_identities)) != len(returned_identities)
        or set(returned_identities) != set(pending_identities)
    ):
        raise ValueError("failed PydanticAI run did not close every deferred tool proposal")
    candidate = (*prior_history, *closing_requests)
    _project_pydantic_history(candidate)
    return candidate


def _pending_tool_parts_from_history(messages: tuple[object, ...]) -> tuple[object, ...]:
    """Return every unresolved proposal from either legal history frontier."""

    if not messages:
        return ()
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    response = messages[-1]
    if not isinstance(response, ModelResponse):
        # An exhausted output-validation run may leave the prior ToolCall
        # closed by its exact SDK ToolReturn without accepting a replacement
        # call.  The next fresh-World turn therefore has no deferred result.
        _project_pydantic_history(messages)
        return ()
    calls = tuple(part for part in response.parts if isinstance(part, ToolCallPart))
    call_ids = tuple(call.tool_call_id for call in calls)
    if not calls or len(set(call_ids)) != len(call_ids) or any(not item for item in call_ids):
        raise ValueError("model message history must end with unique proposed tool calls")
    return calls


def _pending_call_from_history(messages: tuple[object, ...]) -> ToolCall | None:
    """Return the selected first call from the unresolved proposal response."""

    calls = _pending_tool_parts_from_history(messages)
    if not calls:
        return None
    call = calls[0]
    return ToolCall(call.tool_name, call.args_as_dict(raise_if_invalid=True), call.tool_call_id)


def _normalize_pydantic_history_for_current_task(
    messages: tuple[object, ...],
    *,
    task_plan: Mapping[str, object],
) -> tuple[object, ...]:
    """Keep one current task anchor and make all other user turns World-only.

    PydanticAI history is the sole conversation owner.  The ActionPolicy's
    current request still carries the sole fresh World; this projection merely
    removes copies of TaskGoal/GoalPlan from older SDK user turns.  It does not
    synthesize task progress or rewrite any call/result part.
    """

    from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

    anchor_text = json.dumps(task_plan, ensure_ascii=False, separators=(",", ":"))
    normalized = list(messages)
    anchor_index = next(
        (
            index
            for index, message in enumerate(normalized)
            if isinstance(message, ModelRequest) and bool((message.metadata or {}).get(_TASK_ANCHOR_METADATA_KEY))
        ),
        None,
    )
    if anchor_index is None:
        first_user_index = next(
            (
                index
                for index, message in enumerate(normalized)
                if isinstance(message, ModelRequest) and any(isinstance(part, UserPromptPart) for part in message.parts)
            ),
            None,
        )
        if first_user_index is not None:
            first_request = normalized[first_user_index]
            assert isinstance(first_request, ModelRequest)
            normalized[first_user_index] = replace(
                first_request,
                parts=(UserPromptPart(anchor_text), *first_request.parts),
                metadata={
                    **(first_request.metadata or {}),
                    _TASK_ANCHOR_METADATA_KEY: True,
                },
            )
            anchor_index = first_user_index
        else:
            insertion = 0
            while insertion < len(normalized):
                message = normalized[insertion]
                if (
                    not isinstance(message, ModelRequest)
                    or not message.parts
                    or not all(isinstance(part, SystemPromptPart) for part in message.parts)
                ):
                    break
                insertion += 1
            normalized.insert(
                insertion,
                ModelRequest(
                    parts=[UserPromptPart(anchor_text)],
                    metadata={_TASK_ANCHOR_METADATA_KEY: True},
                ),
            )
            anchor_index = insertion

    for index, message in enumerate(tuple(normalized)):
        if not isinstance(message, ModelRequest):
            continue
        prompts = tuple(part for part in message.parts if isinstance(part, UserPromptPart))
        if not prompts:
            continue
        if index == anchor_index:
            if len(prompts) not in {1, 2}:
                raise ValueError("task anchor request has an invalid prompt count")
            anchor = prompts[0]
            parts = tuple(replace(part, content=anchor_text) if part is anchor else part for part in message.parts)
            metadata = {**(message.metadata or {}), _TASK_ANCHOR_METADATA_KEY: True}
            message = replace(message, parts=parts, metadata=metadata)
            normalized[index] = message
            prompts = tuple(part for part in message.parts if isinstance(part, UserPromptPart))[1:]
        elif len(prompts) != 1:
            raise ValueError("PydanticAI history request has multiple World prompts")
        for prompt in prompts:
            payload = _prompt_json_object(prompt)
            if payload is None or "observation" not in payload:
                continue
            current_turn = {"observation": payload["observation"]}
            if payload.get("control_feedback"):
                current_turn["control_feedback"] = payload["control_feedback"]
            current_text = json.dumps(current_turn, ensure_ascii=False, separators=(",", ":"))
            message = normalized[index]
            assert isinstance(message, ModelRequest)
            parts = tuple(
                _replace_prompt_text(part, current_text) if part is prompt else part for part in message.parts
            )
            normalized[index] = replace(message, parts=parts)
    return tuple(normalized)


def _fold_expired_world_prompts(
    messages: tuple[object, ...],
    *,
    max_estimated_tokens: int,
) -> tuple[object, ...]:
    """Remove historical World prompts while preserving exact SDK exchanges.

    ``TurnPacker`` supplies the one authoritative fresh World after this
    history processor runs.  Retaining any older World here duplicates a
    temporal observation and makes the provider prefix slide every turn.
    TaskGoal/GoalPlan remain in the separately marked task anchor; ToolCall,
    ToolReturn, model conclusions, and the unresolved call suffix are not
    changed.
    """

    if max_estimated_tokens < 1:
        raise ValueError("recent World history target must be positive")
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    candidates: list[tuple[int, UserPromptPart]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, ModelRequest):
            continue
        prompts = tuple(part for part in message.parts if isinstance(part, UserPromptPart))
        if not prompts:
            continue
        if bool((message.metadata or {}).get(_TASK_ANCHOR_METADATA_KEY)):
            if len(prompts) not in {1, 2}:
                raise ValueError("task anchor request has an invalid prompt count")
            prompts = prompts[1:]
        elif len(prompts) != 1:
            raise ValueError("PydanticAI history request has multiple World prompts")
        for prompt in prompts:
            candidates.append((index, prompt))
    if not candidates:
        return messages

    expired = {id(prompt) for _index, prompt in candidates}
    folded: list[object] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            folded.append(message)
            continue
        parts = tuple(part for part in message.parts if not (isinstance(part, UserPromptPart) and id(part) in expired))
        if parts:
            folded.append(replace(message, parts=parts))
    return tuple(folded)


def _project_expired_history(
    messages: tuple[object, ...],
    *,
    max_estimated_tokens: int,
    current_world_observation_id: str = "",
) -> tuple[object, ...]:
    """Project bounded semantic history plus an exact current-world suffix.

    Historical World prompts are temporal observations and are removed because
    TurnPacker supplies exactly one fresh World.  Closed exchanges retain their
    ToolCall/ToolReturn identity and semantic values, but observation-local refs
    are removed once the exchange's World is not the current World.  Same-world
    reads and the unresolved response remain exact.  A completed response may
    also drop private ``ThinkingPart`` only when the same response already
    carries a public conclusion.  Harness remains the only semantic compactor.
    """

    folded = _fold_expired_world_prompts(
        messages,
        max_estimated_tokens=max_estimated_tokens,
    )
    projected = _deground_expired_tool_exchanges(
        folded,
        current_world_observation_id=current_world_observation_id,
    )
    projected = _strip_completed_private_reasoning(projected)
    return _deduplicate_expired_model_prose(
        projected,
        max_estimated_tokens=max_estimated_tokens,
    )


def _deground_expired_tool_exchanges(
    messages: tuple[object, ...],
    *,
    current_world_observation_id: str,
) -> tuple[object, ...]:
    """Remove stale operational handles without changing call/result pairing."""

    if not messages or not current_world_observation_id:
        return messages
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
    )

    expired_call_ids: set[str] = set()
    expired_return_ids: set[str] = set()
    for _response, returns in _completed_tool_exchanges(messages):
        for part in returns:
            if not isinstance(part, ToolReturnPart) or not isinstance(part.metadata, Mapping):
                continue
            before_world = str(part.metadata.get("before_world", ""))
            after_world = str(part.metadata.get("after_world", ""))
            if before_world and before_world != current_world_observation_id:
                expired_call_ids.add(part.tool_call_id)
            if after_world and after_world != current_world_observation_id:
                expired_return_ids.add(part.tool_call_id)
    if not expired_call_ids and not expired_return_ids:
        return _deground_compaction_summaries(messages)

    projected: list[object] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            response_expired = any(
                isinstance(part, ToolCallPart) and part.tool_call_id in expired_call_ids for part in message.parts
            )
            if not response_expired:
                projected.append(message)
                continue
            parts: list[object] = []
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_call_id in expired_call_ids:
                    parts.append(replace(part, args=sanitize_history_value(part.args)))
                elif response_expired and isinstance(part, (TextPart, ThinkingPart)):
                    content = str(sanitize_history_value(part.content))
                    if content:
                        parts.append(replace(part, content=content))
                else:
                    parts.append(part)
            projected.append(replace(message, parts=tuple(parts)))
            continue
        if isinstance(message, ModelRequest):
            if not any(
                isinstance(part, ToolReturnPart) and part.tool_call_id in expired_return_ids for part in message.parts
            ):
                projected.append(message)
                continue
            parts = tuple(
                replace(part, content=sanitize_history_value(part.content))
                if isinstance(part, ToolReturnPart) and part.tool_call_id in expired_return_ids
                else part
                for part in message.parts
            )
            projected.append(replace(message, parts=parts))
            continue
        projected.append(message)
    return _deground_compaction_summaries(tuple(projected))


def _deground_compaction_summaries(messages: tuple[object, ...]) -> tuple[object, ...]:
    """Keep Harness summaries semantic if an older run emitted a local ref."""

    from pydantic_ai.messages import ModelRequest, SystemPromptPart

    projected: list[object] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            projected.append(message)
            continue
        parts: list[object] = []
        changed = False
        for part in message.parts:
            if isinstance(part, SystemPromptPart) and part.content.startswith("Summary of previous conversation"):
                content = str(sanitize_history_value(part.content))
                if content != part.content:
                    changed = True
                    parts.append(replace(part, content=content))
                    continue
            parts.append(part)
        projected.append(replace(message, parts=tuple(parts)) if changed else message)
    return tuple(projected)


def _strip_completed_private_reasoning(
    messages: tuple[object, ...],
) -> tuple[object, ...]:
    """Keep public conclusions while expiring private reasoning from closed exchanges.

    The response whose ToolReturn will be delivered on the next physical call
    remains byte-for-byte exact.  Older responses are eligible only after a
    same-ID ToolReturn has closed their tool exchange, and only when their own
    public text already carries the model-visible conclusion.  Tool-only
    reasoning therefore remains available until Harness can summarize it.
    """

    if not messages:
        return messages
    from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

    completed_response_ids = {id(response) for response, _returns in _completed_tool_exchanges(messages)}
    if not completed_response_ids:
        return messages
    projected = list(messages)
    for index, message in enumerate(messages):
        if not isinstance(message, ModelResponse) or id(message) not in completed_response_ids:
            continue
        if not any(isinstance(part, TextPart) and part.content.strip() for part in message.parts):
            continue
        parts = tuple(part for part in message.parts if not isinstance(part, ThinkingPart))
        if parts != tuple(message.parts):
            projected[index] = replace(message, parts=parts)
    return tuple(projected)


def _deduplicate_expired_model_prose(
    messages: tuple[object, ...],
    *,
    max_estimated_tokens: int,
) -> tuple[object, ...]:
    """Remove only repeated old prose while preserving a raw recent suffix."""

    if max_estimated_tokens < 1:
        raise ValueError("recent history target must be positive")
    if len(messages) <= 1:
        return messages
    from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

    recent_start = _recent_history_start(
        messages,
        max_estimated_tokens=max_estimated_tokens,
    )

    seen: set[tuple[type[object], str]] = set()
    projected = list(messages)
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, ModelResponse):
            continue
        parts: list[object] = []
        for part in reversed(message.parts):
            if not isinstance(part, (TextPart, ThinkingPart)):
                parts.append(part)
                continue
            signature = (type(part), " ".join(part.content.split()))
            keep = index >= recent_start or signature not in seen
            seen.add(signature)
            if keep:
                parts.append(part)
        ordered = tuple(reversed(parts))
        if ordered != tuple(message.parts):
            projected[index] = replace(message, parts=ordered)
    return tuple(projected)


def _recent_history_start(
    messages: tuple[object, ...],
    *,
    max_estimated_tokens: int,
) -> int:
    """Return the start of a non-empty raw suffix within the shared token target."""

    if max_estimated_tokens < 1:
        raise ValueError("recent history target must be positive")
    if not messages:
        return 0
    from pydantic_ai_harness.compaction import estimate_token_count

    recent_start = len(messages) - 1
    used = 0
    for index in range(len(messages) - 1, -1, -1):
        message_tokens = estimate_token_count([messages[index]])
        if used and used + message_tokens > max_estimated_tokens:
            break
        recent_start = index
        used += message_tokens
    return recent_start


def _history_economy_compaction_required(
    messages: tuple[object, ...],
    *,
    max_estimated_tokens: int,
    available_history_tokens: int,
    observed_history_tokens: int,
) -> bool:
    """Request Harness only after a useful pair-safe history batch expires.

    The high watermark bounds steady-state history cost.  The independent
    minimum reclaim watermark is the hysteresis: a compacted summary plus a
    small amount of new history cannot immediately schedule another provider
    call.  This schedule depends only on typed history size, never task or page
    semantics.
    """

    if (
        not messages
        or max_estimated_tokens < 1
        or available_history_tokens < 1
        or observed_history_tokens < int(available_history_tokens * _HISTORY_ECONOMY_PRESSURE_RATIO)
    ):
        return False
    from pydantic_ai.messages import ModelRequest, SystemPromptPart
    from pydantic_ai_harness.compaction import estimate_token_count

    recent_start = _recent_history_start(
        messages,
        max_estimated_tokens=max_estimated_tokens,
    )
    reclaimable = tuple(
        message
        for message in messages[:recent_start]
        if not (
            isinstance(message, ModelRequest)
            and (
                bool((message.metadata or {}).get(_TASK_ANCHOR_METADATA_KEY))
                or (bool(message.parts) and all(isinstance(part, SystemPromptPart) for part in message.parts))
            )
        )
    )
    minimum_reclaim = max(
        1,
        int(available_history_tokens * _HISTORY_COMPACTION_MIN_RECLAIM_RATIO),
    )
    return bool(reclaimable and estimate_token_count(reclaimable) >= minimum_reclaim)


def _prompt_json_object(prompt: object) -> dict[str, object] | None:
    from pydantic_ai.messages import TextContent, UserPromptPart

    if not isinstance(prompt, UserPromptPart):
        return None
    content = prompt.content
    items = (content,) if isinstance(content, str) else tuple(content)
    text = next(
        (
            item if isinstance(item, str) else item.content if isinstance(item, TextContent) else None
            for item in items
            if isinstance(item, (str, TextContent))
        ),
        None,
    )
    if not isinstance(text, str):
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _replace_prompt_text(prompt: object, text: str):
    from pydantic_ai.messages import TextContent, UserPromptPart

    if not isinstance(prompt, UserPromptPart):
        return prompt
    if isinstance(prompt.content, str):
        return replace(prompt, content=text)
    replaced_text = False
    content: list[Any] = []
    for item in prompt.content:
        if not replaced_text and isinstance(item, str):
            content.append(text)
            replaced_text = True
        elif not replaced_text and isinstance(item, TextContent):
            content.append(replace(item, content=text))
            replaced_text = True
        else:
            content.append(item)
    if not replaced_text:
        content.insert(0, text)
    return replace(prompt, content=content)


def _accepted_message_history(
    result,
    prior_history: tuple[object, ...],
    accepted: AcceptedToolExchange,
    pending_calls: tuple[object, ...],
) -> tuple[object, ...]:
    """Keep the SDK's complete fresh-World turn and replace only its accepted response."""

    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    new_messages = tuple(result.new_messages())
    if not new_messages or not isinstance(new_messages[-1], ModelResponse):
        raise ValueError("PydanticAI did not return one complete current turn")
    requests: list[object] = []
    rejected_response_count = 0
    retry_prompt_count = 0
    for message in new_messages[:-1]:
        if isinstance(message, ModelResponse):
            if any(isinstance(part, ToolCallPart) for part in message.parts):
                raise ValueError("PydanticAI output retry cannot discard a tool-call response")
            rejected_response_count += 1
            continue
        if not isinstance(message, ModelRequest):
            raise ValueError("PydanticAI returned an unsupported current-turn message")
        retry_parts = tuple(part for part in message.parts if isinstance(part, RetryPromptPart))
        if retry_parts:
            if len(retry_parts) != len(message.parts):
                raise ValueError("PydanticAI output retry request mixed canonical context")
            retry_prompt_count += 1
            continue
        requests.append(message)
    if rejected_response_count != retry_prompt_count or rejected_response_count > 1:
        raise ValueError("PydanticAI output retry history is incomplete or unbounded")
    requests_tuple = tuple(requests)
    if not any(isinstance(part, UserPromptPart) for message in requests_tuple for part in message.parts):
        raise ValueError("PydanticAI current turn lost its fresh World prompt")
    if not pending_calls:
        if any(isinstance(part, ToolReturnPart) for message in requests_tuple for part in message.parts):
            raise ValueError("PydanticAI turn without a pending call cannot contain a deferred result")
        candidate = (*prior_history, *requests_tuple, accepted.response)
        _project_pydantic_history(candidate)
        return candidate

    pending_identities = tuple((part.tool_name, part.tool_call_id) for part in pending_calls)
    matching_parts = tuple(
        part
        for message in requests_tuple
        for part in message.parts
        if isinstance(part, ToolReturnPart) and (part.tool_name, part.tool_call_id) in set(pending_identities)
    )
    returned_by_identity = {(part.tool_name, part.tool_call_id): part for part in matching_parts}
    if (
        len(matching_parts) != len(pending_identities)
        or len(returned_by_identity) != len(pending_identities)
        or set(returned_by_identity) != set(pending_identities)
    ):
        raise ValueError("PydanticAI did not close every deferred tool proposal")
    return (
        *prior_history,
        *requests_tuple,
        accepted.response,
    )


def _completed_tool_exchanges(
    messages: tuple[object, ...],
) -> tuple[tuple[object, tuple[object, ...]], ...]:
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

    completed: list[tuple[object, tuple[object, ...]]] = []
    pending_response = None
    for message in messages:
        if isinstance(message, ModelResponse) and any(isinstance(part, ToolCallPart) for part in message.parts):
            pending_response = message
            continue
        if pending_response is None or not isinstance(message, ModelRequest):
            continue
        returns = tuple(part for part in message.parts if isinstance(part, ToolReturnPart))
        if returns:
            completed.append((pending_response, returns))
            pending_response = None
    return tuple(completed)


def _completed_exchange_count(messages: tuple[object, ...]) -> int:
    return len(_completed_tool_exchanges(messages))


def _history_compaction_required(
    breakdown: ModelRequestBreakdown,
    *,
    has_history: bool,
) -> bool:
    """Return the request-capacity arm of the history compaction schedule."""

    return bool(
        has_history
        and breakdown.history_tokens > 0
        and breakdown.estimated_input_tokens
        >= int(breakdown.effective_input_limit * _HISTORY_COMPACTION_PRESSURE_RATIO)
    )


def _available_history_tokens(breakdown: ModelRequestBreakdown) -> int:
    non_history_tokens = max(
        0,
        breakdown.estimated_input_tokens - breakdown.history_tokens,
    )
    return max(1, breakdown.effective_input_limit - non_history_tokens)


async def _compact_pydantic_history(
    messages: tuple[object, ...],
    *,
    model: object,
    max_estimated_tokens: int,
    observed_estimated_tokens: int | None = None,
    timeout_s: float,
    trigger: str = "token_pressure",
) -> _HistoryCompactionRun:
    """Use Harness to summarize only a pressured, pair-safe expired history prefix."""

    if not messages:
        return _HistoryCompactionRun(())
    if max_estimated_tokens < 1:
        raise ValueError("history soft target must be positive")
    if timeout_s <= 0:
        raise ValueError("history compaction timeout must be positive")
    if trigger not in {"token_pressure", "history_pressure"}:
        raise ValueError("history compaction trigger is unsupported")
    from pydantic_ai import capture_run_messages
    from pydantic_ai.usage import RunUsage
    from pydantic_ai_harness.compaction import (
        SummarizingCompaction,
        compact_now,
        estimate_token_count,
    )

    activation_ratio = (
        _HISTORY_COMPACTION_PRESSURE_RATIO if trigger == "token_pressure" else _HISTORY_ECONOMY_PRESSURE_RATIO
    )
    activation_threshold = max(
        1,
        int(max_estimated_tokens * activation_ratio),
    )
    estimated_tokens = (
        estimate_token_count(messages) if observed_estimated_tokens is None else observed_estimated_tokens
    )
    if estimated_tokens < activation_threshold:
        return _HistoryCompactionRun(messages)
    compaction_target = max(
        1,
        int(max_estimated_tokens * _HISTORY_COMPACTION_TARGET_RATIO),
    )
    strategy = SummarizingCompaction(
        model=model,
        max_tokens=compaction_target,
        keep_tokens=max(
            1,
            int(max_estimated_tokens * _HISTORY_RECENT_EXACT_TOKENS_RATIO),
        ),
        summary_prompt=_HISTORY_COMPACTION_SUMMARY_PROMPT,
        instructions=_HISTORY_COMPACTION_INSTRUCTIONS,
        preserve_first_user_message=True,
        incremental=True,
        receipts=False,
    )
    started = time.perf_counter()
    with capture_run_messages() as transcript:
        try:
            async with asyncio.timeout(timeout_s):
                compacted = await compact_now(
                    strategy,
                    list(messages),
                    model=model,
                    usage=RunUsage(),
                )
            if transcript:
                preserved_count = _shared_history_suffix_count(
                    messages,
                    tuple(compacted[1:]),
                )
                extra_end = len(compacted) - preserved_count
                preserved_extras = tuple(compacted[1:extra_end])
                if len(preserved_extras) > 1:
                    raise ValueError("Harness compaction returned unsupported preserved messages")
                exact_extras: list[object] = []
                for extra in preserved_extras:
                    source_index = next(
                        (index for index, item in enumerate(messages) if item is extra or item == extra),
                        None,
                    )
                    if source_index is None:
                        raise ValueError("Harness compaction invented a preserved message")
                    exact_extras.append(messages[source_index])
                compacted = [
                    compacted[0],
                    *exact_extras,
                    *(messages[-preserved_count:] if preserved_count else ()),
                ]
            else:
                compacted = list(messages)
            before_pending = tuple(
                (part.tool_name, part.tool_call_id) for part in _pending_tool_parts_from_history(messages)
            )
            after_pending = tuple(
                (part.tool_name, part.tool_call_id) for part in _pending_tool_parts_from_history(tuple(compacted))
            )
            if before_pending != after_pending:
                raise ValueError("Harness compaction changed the unresolved tool-call suffix")
            # Harness owns the pair-safe cutoff.  Validate the complete output
            # at the same history-conversion boundary before it can replace the
            # canonical SDK history.  A third-party regression therefore falls
            # back to the exact input history instead of reaching TurnPacker as
            # an orphaned ToolCall/ToolReturn sequence.
            _project_pydantic_history(tuple(compacted))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return _HistoryCompactionRun(
                messages,
                tuple(transcript),
                error=f"{type(exc).__name__}: {str(exc)[:360]}",
                latency_ms=(time.perf_counter() - started) * 1000,
                attempted=bool(transcript),
                trigger=trigger,
            )
    return _HistoryCompactionRun(
        tuple(compacted),
        tuple(transcript),
        latency_ms=(time.perf_counter() - started) * 1000,
        attempted=bool(transcript),
        trigger=trigger,
    )


def _shared_history_suffix_count(
    source: tuple[object, ...],
    candidate: tuple[object, ...],
) -> int:
    """Return the exact tail Harness preserved after its optional task anchor."""

    maximum = min(len(source), len(candidate))
    for count in range(maximum, -1, -1):
        if count == 0 or source[-count:] == candidate[-count:]:
            return count
    return 0


def _repair_preserves_rejected_semantics(
    error: GroundedToolResolutionError | None,
    rejected_calls: tuple[ToolCall, ...],
    repaired_call: ToolCall,
    specs: tuple[object, ...],
) -> bool:
    """Admit representation repair only when semantics came from the rejected envelope."""

    if not rejected_calls:
        return False
    if len(rejected_calls) != 1:
        return False
    rejected = rejected_calls[0]
    # A repair is a separate physical provider response, so its ToolCall owns
    # a new provider-generated call ID.  That wire identity is not a semantic
    # operand.  The accepted repair response and its eventual ToolReturn use
    # the new ID; operation and every schema-declared argument remain fixed by
    # the pruning check below.
    if repaired_call.name != rejected.name:
        return False
    spec = next((item for item in specs if getattr(item, "name", None) == rejected.name), None)
    if spec is None:
        return False
    return _is_representation_pruning(
        rejected.arguments,
        repaired_call.arguments,
        getattr(spec, "input_schema", {}),
    )


def _is_representation_pruning(
    rejected: object,
    repaired: object,
    schema: object,
) -> bool:
    """Allow removal only of fields absent from the offered tool schema."""

    if isinstance(rejected, Mapping) and isinstance(repaired, Mapping):
        schema_mapping = schema if isinstance(schema, Mapping) else {}
        properties_value = schema_mapping.get("properties", {})
        properties = properties_value if isinstance(properties_value, Mapping) else {}
        if any(key in properties and key not in repaired for key in rejected):
            return False
        return all(
            key in rejected and _is_representation_pruning(rejected[key], value, properties.get(key, {}))
            for key, value in repaired.items()
        )
    if isinstance(rejected, (list, tuple)) and isinstance(repaired, (list, tuple)):
        item_schema = schema.get("items", {}) if isinstance(schema, Mapping) else {}
        return len(rejected) == len(repaired) and all(
            _is_representation_pruning(before, after, item_schema)
            for before, after in zip(rejected, repaired, strict=True)
        )
    return type(rejected) is type(repaired) and rejected == repaired


def _representation_repair_prompt(rejected_calls, error, specs) -> str:
    calls = tuple(
        {"name": call.name, "arguments": to_json_compatible(call.arguments)} for call in tuple(rejected_calls)[:1]
    )
    schema = tuple(
        {
            "name": spec.name,
            "input_schema": to_json_compatible(spec.input_schema),
        }
        for spec in specs
    )
    return json.dumps(
        {
            "violation": error.code.value if error is not None else "provider_envelope_invalid",
            "rejected_calls": calls,
            "closed_tools": schema,
            "instruction": "Return exactly one representation-only repaired tool call.",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _reconciliation_error(reconciliation) -> GroundedToolResolutionError:
    code = (
        GroundedToolResolutionCode.UNKNOWN_OPERATION
        if str(reconciliation.issue_code) == "unknown_tool"
        else GroundedToolResolutionCode.STALE_CATALOG
        if str(reconciliation.issue_code) == "stale_catalog"
        else GroundedToolResolutionCode.INVALID_ARGUMENTS
    )
    detail = reconciliation.argument_code
    if reconciliation.field_paths:
        detail = f"{detail}:{','.join(reconciliation.field_paths)}" if detail else ",".join(reconciliation.field_paths)
    return GroundedToolResolutionError(code, detail)


def _tool_resolution_failure(error: GroundedToolResolutionError | None) -> ModelFailure:
    if error is None:
        return _failure(
            ModelFailureKind.SCHEMA_ERROR,
            "model did not produce one valid current tool call",
        )
    if error.code is GroundedToolResolutionCode.GROUNDING_GAP:
        return _failure(ModelFailureKind.TOOL_GROUNDING_GAP, str(error))
    return _failure(ModelFailureKind.INVALID_TOOL_ARGUMENTS, str(error))


def _pydantic_model_boundary_codec(
    envelope: CanonicalProviderEnvelope,
    binary_content_type,
    deferred_tool_results_type,
    external_toolset_type,
    tool_failed_type,
    tool_return_type,
    tool_definition_type,
):
    """Losslessly convert one admitted envelope to PydanticAI typed values."""

    if len(envelope.instructions) != 1:
        raise ValueError("PydanticAI ActionPolicy codec requires one ordered instruction")
    prompt: object
    if envelope.media:
        prompt = [
            envelope.user_text,
            *(binary_content_type(data=item.data, media_type=item.mime_type) for item in envelope.media),
        ]
    else:
        prompt = envelope.user_text
    toolset = external_toolset_type(
        [
            tool_definition_type(
                name=item.name,
                description=item.description,
                parameters_json_schema=to_json_compatible(item.parameters_json_schema),
                strict=item.strict,
            )
            for item in envelope.function_tools
        ],
        id=envelope.catalog.catalog_id,
    )
    message_history = list(envelope.pydantic_history)
    deferred_results = None
    if envelope.deferred_tool_returns:
        actual_call_id = str(envelope.tool_result["tool_call_id"])
        calls = {}
        for item in envelope.deferred_tool_returns:
            call_id = str(item["tool_call_id"])
            if item.get("outcome") == "failed":
                calls[call_id] = tool_failed_type(UNEXECUTED_TOOL_CALL_MESSAGE)
                continue
            calls[call_id] = tool_return_type(
                return_value=to_json_compatible(item["return_value"]),
                metadata=(to_json_compatible(envelope.tool_result_metadata) if call_id == actual_call_id else None),
            )
        deferred_results = deferred_tool_results_type(calls=calls)
    return envelope.instructions[0], prompt, toolset, message_history, deferred_results


def _attempt_token_delta(
    previous_attempts: tuple[ModelGenerationAttempt, ...],
    response: Mapping[str, object],
    usage: object,
    field_name: str,
) -> tuple[int, int]:
    response_value = _response_usage_int(response, field_name)
    raw_cumulative = _usage_int(usage, field_name)
    if response_value >= 0:
        return response_value, raw_cumulative
    previous = sum(
        (item.prompt_tokens if field_name == "input_tokens" else item.completion_tokens) for item in previous_attempts
    )
    return max(0, raw_cumulative - previous), raw_cumulative


def _response_usage_int(response: Mapping[str, object], field_name: str) -> int:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return -1
    value = usage.get(field_name)
    return value if type(value) is int and value >= 0 else -1


def _response_reasoning_observation(response: Mapping[str, object]) -> tuple[bool, int]:
    """Read PydanticAI's typed reasoning part and normalized usage details."""

    parts = response.get("parts")
    reasoning_content_present = bool(
        isinstance(parts, list)
        and any(
            isinstance(part, Mapping)
            and part.get("part_kind") == "thinking"
            and bool(str(part.get("content") or "").strip())
            for part in parts
        )
    )
    usage = response.get("usage")
    details = usage.get("details") if isinstance(usage, Mapping) else None
    value = details.get("reasoning_tokens") if isinstance(details, Mapping) else None
    reasoning_tokens = value if type(value) is int and value >= 0 else 0
    return reasoning_content_present, reasoning_tokens


def _action_policy_physical_settings(
    envelope: CanonicalProviderEnvelope,
    *,
    require_action: bool,
) -> dict[str, object]:
    """Return the one provider-compatible physical profile for this logical turn."""

    settings = dict(envelope.model_settings)
    if require_action:
        # DeepSeek rejects required tool choice while thinking is enabled.
        # The fallback preserves the same semantic envelope and current World,
        # but trades further reasoning for one complete action envelope.
        settings["thinking"] = False
        settings["tool_choice"] = "required"
    else:
        settings["tool_choice"] = "auto"
    return settings


def _serialized_current_pydantic_invocation(
    messages: tuple[object, ...],
    *,
    max_response_count: int,
) -> list[dict[str, object]]:
    """Project only the SDK messages produced by one physical run identity."""

    if not messages:
        return []
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    serialized = json.loads(ModelMessagesTypeAdapter.dump_json(list(messages)))
    return _captured_invocation_messages(serialized, max_response_count=max_response_count)


def _captured_output_failure(
    messages: list[dict[str, object]],
) -> tuple[int, StructuredOutputFailureKind | None]:
    """Classify the final physical output without reinterpreting its semantics."""

    responses = tuple(message for message in messages if message.get("kind") == "response")
    if not responses:
        return 0, None
    parts = responses[-1].get("parts")
    parts = parts if isinstance(parts, list) else []
    has_tool_call = any(
        isinstance(part, Mapping) and part.get("part_kind") == "tool-call"
        for part in parts
    )
    return len(responses), _structured_output_failure_for_response(
        responses[-1],
        has_tool_call=has_tool_call,
    )


def _structured_output_failure_for_response(
    response: Mapping[str, object],
    *,
    has_tool_call: bool,
) -> StructuredOutputFailureKind:
    finish_reason = str(response.get("finish_reason") or "").casefold()
    if finish_reason in {"length", "max_tokens"}:
        return StructuredOutputFailureKind.OUTPUT_TRUNCATED
    if not has_tool_call:
        return StructuredOutputFailureKind.NO_TOOL_CALL
    return StructuredOutputFailureKind.JSON_INVALID


def _captured_invocation_messages(
    captured: list[dict[str, object]],
    *,
    max_response_count: int,
) -> list[dict[str, object]]:
    """Return only messages stamped by the failed PydanticAI run.

    ``capture_run_messages`` intentionally includes normalized supplied
    history.  A response-count suffix is ambiguous whenever the current run
    ends before using its retry budget, so the SDK-owned ``run_id`` is the
    currentness authority.
    """

    if max_response_count <= 0:
        raise ValueError("captured invocation response bound must be positive")
    current_run_id = next(
        (str(message.get("run_id") or "") for message in reversed(captured) if message.get("run_id")),
        "",
    )
    if not current_run_id:
        raise ValueError("captured PydanticAI invocation has no run identity")
    current = [message for message in captured if str(message.get("run_id") or "") == current_run_id]
    response_count = sum(message.get("kind") == "response" for message in current)
    if response_count > max_response_count:
        raise ValueError("captured PydanticAI invocation exceeds its response bound")
    return current


def _latest_structured_output_failure(
    attempts: tuple[ModelGenerationAttempt, ...],
) -> StructuredOutputFailureKind | None:
    return next(
        (attempt.output_failure_kind for attempt in reversed(attempts) if attempt.output_failure_kind is not None),
        None,
    )


def _usage_int(usage: object, field_name: str) -> int:
    value = getattr(usage, field_name, 0)
    return value if type(value) is int and value >= 0 else 0


def _tool_transcript(specs: tuple[object, ...]) -> list[dict[str, object]]:
    return [
        {
            "tool.name": getattr(spec, "name", ""),
            "tool.description": getattr(spec, "description", ""),
            "tool.json_schema": to_json_compatible(
                getattr(spec, "parameters_json_schema", getattr(spec, "input_schema", {}))
            ),
        }
        for spec in specs
    ]


def _classify_provider_failure(error: Exception) -> _ProviderFailureDetail:
    status_code = _provider_status_code(error)
    retry_after_s = _provider_retry_after_s(error)
    exception_class = type(error).__name__
    names = " ".join(type(item).__name__.casefold() for item in _exception_chain(error))
    if status_code == 429:
        return _ProviderFailureDetail(
            ProviderFailureCode.RATE_LIMITED,
            True,
            "model provider rate limited the decision request",
            exception_class,
            status_code,
            retry_after_s,
        )
    if status_code in {401, 403}:
        return _ProviderFailureDetail(
            ProviderFailureCode.AUTHENTICATION,
            False,
            "model provider authentication failed",
            exception_class,
            status_code,
        )
    if status_code is not None and 400 <= status_code < 500 and status_code not in {408, 409}:
        return _ProviderFailureDetail(
            ProviderFailureCode.INVALID_REQUEST,
            False,
            "model provider rejected the decision request",
            exception_class,
            status_code,
        )
    if status_code == 408 or "timeout" in names:
        return _ProviderFailureDetail(
            ProviderFailureCode.TIMEOUT,
            True,
            "model provider decision request timed out",
            exception_class,
            status_code,
            retry_after_s,
        )
    if "connection" in names or "transport" in names:
        return _ProviderFailureDetail(
            ProviderFailureCode.TRANSPORT,
            True,
            "model provider transport failed",
            exception_class,
            status_code,
            retry_after_s,
        )
    return _ProviderFailureDetail(
        ProviderFailureCode.UNAVAILABLE,
        status_code is None or status_code == 409 or status_code >= 500,
        "model provider is unavailable",
        exception_class,
        status_code,
        retry_after_s,
    )


def _exception_chain(error: Exception) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _provider_status_code(error: Exception) -> int | None:
    for item in _exception_chain(error):
        status = getattr(item, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def _provider_retry_after_s(error: Exception) -> float | None:
    for item in _exception_chain(error):
        headers = getattr(item, "headers", None)
        if not isinstance(headers, Mapping):
            response = getattr(item, "response", None)
            headers = getattr(response, "headers", None)
        if not isinstance(headers, Mapping):
            continue
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            delay = float(value)
        except (TypeError, ValueError):
            continue
        if delay >= 0:
            return delay
    return None


def _failure(
    kind: ModelFailureKind,
    reason: str,
    *,
    retryable: bool = False,
    provider_code: ProviderFailureCode | None = None,
    retry_after_s: float | None = None,
    attempt_origin: ProviderAttemptOrigin = ProviderAttemptOrigin.NETWORK,
) -> ModelFailure:
    return ModelFailure(
        kind,
        reason,
        retryable,
        provider_code,
        retry_after_s,
        attempt_origin=attempt_origin,
    )


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required model configuration: {name}")
    return value


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _zhipu_supports_multimodal(model_id: str) -> bool:
    return "v" in model_id.casefold().split("-", 2)[-1]


__all__ = [
    "PydanticAIGroundedDecisionPort",
    "openai_compatible_pydantic_ai_policy_from_environment",
    "zhipu_pydantic_ai_policy_from_environment",
]
