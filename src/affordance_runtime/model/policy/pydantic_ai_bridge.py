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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

from affordance_runtime.agent.context.context import AgentImageInput
from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from affordance_runtime.model.policy.grounded_policy_context import (
    GroundedPolicyContextBinder,
)
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_action_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall

_MAX_PROVIDER_RETRIES = 1
_DEFAULT_PROVIDER_BACKOFF_S = 1.0
_MAX_PROVIDER_BACKOFF_S = 5.0
_ACTION_MODEL_SETTINGS = {
    "thinking": False,
    "max_tokens": 1024,
    "temperature": 0.0,
}


@dataclass(frozen=True)
class _ProviderFailureDetail:
    code: ProviderFailureCode
    retryable: bool
    reason: str
    exception_class: str
    status_code: int | None = None
    retry_after_s: float | None = None


class _ProviderCallExhausted(RuntimeError):
    def __init__(self, detail: _ProviderFailureDetail) -> None:
        super().__init__(detail.reason)
        self.detail = detail


@dataclass(frozen=True)
class PydanticAIGroundedDecisionPort:
    """Resolve exactly one current external tool call into a Runtime decision."""

    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_multimodal: bool
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    transport_timeout_s: float = 85.0
    provider_retry_backoff_s: float = _DEFAULT_PROVIDER_BACKOFF_S
    max_provider_retry_delay_s: float = _MAX_PROVIDER_BACKOFF_S
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_catalog_specs: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_provider_retry_count: int = field(default=0, init=False, compare=False)
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )
    last_invocation_result: ModelInvocationResult[ResolvedModelDecision] | None = field(
        default=None, init=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip() or not self.endpoint_host.strip():
            raise ValueError("PydanticAI model identity is required")
        if not 0 < self.transport_timeout_s <= 300:
            raise ValueError("PydanticAI transport timeout must be in (0, 300]")
        if not 0 <= self.provider_retry_backoff_s <= self.max_provider_retry_delay_s:
            raise ValueError("provider retry backoff must fit its bounded delay")
        if not 0 < self.max_provider_retry_delay_s <= _MAX_PROVIDER_BACKOFF_S:
            raise ValueError("provider retry delay must be in (0, 5]")
        object.__setattr__(self, "perception_profile", DecisionPerceptionProfile(self.perception_profile))

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return GROUNDED_ACTION_DECISION_CAPABILITIES

    @property
    def supports_final_response(self) -> bool:
        return True

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
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_catalog_specs", ())
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_model_call_count", 0)
        object.__setattr__(self, "last_provider_retry_count", 0)
        object.__setattr__(self, "last_generation_attempts", ())
        object.__setattr__(self, "last_invocation_result", None)
        try:
            from pydantic_ai import (
                Agent,
                BinaryContent,
                DeferredToolRequests,
                DeferredToolResults,
                ExternalToolset,
                ModelRetry,
                ToolDefinition,
            )
            from pydantic_ai.exceptions import (
                ModelAPIError,
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

        try:
            catalog = compile_grounded_action_catalog(request.agent_context)
            object.__setattr__(self, "last_catalog_count", len(catalog.specs))
            object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
            object.__setattr__(self, "last_catalog_specs", tuple(catalog.specs))
            object.__setattr__(self, "last_image_input_count", len(request.image_inputs))
            messages = self.context_binder.action_messages(
                request,
                catalog.specs,
                supports_multimodal=self.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=False,
            )
            instructions, user_prompt = _pydantic_prompt(messages, request.image_inputs, BinaryContent)
            final_ready = _final_response_ready(request.agent_context)
            if final_ready:
                object.__setattr__(self, "last_catalog_count", 0)
                object.__setattr__(self, "last_catalog_bytes", 0)
                object.__setattr__(self, "last_catalog_specs", ())
            toolset = ExternalToolset(
                [
                    ToolDefinition(
                        name=spec.name,
                        description=spec.description,
                        parameters_json_schema=to_json_compatible(spec.input_schema),
                        strict=True,
                    )
                    for spec in catalog.specs
                ],
                id=catalog.catalog_id,
            )
            agent = Agent(
                self.model,
                instructions=instructions,
                output_type=str if final_ready else [str, DeferredToolRequests],
            )
            usage = RunUsage()
            # Initial decision and tool repair may each make one explicit
            # provider retry. SDK-level retry stays disabled so none of those
            # physical attempts disappear from the trace.
            limits = UsageLimits(request_limit=4)
            result = await self._run_provider_call(
                lambda: agent.run(
                    user_prompt,
                    toolsets=[] if final_ready else [toolset],
                    usage=usage,
                    usage_limits=limits,
                    model_settings=_ACTION_MODEL_SETTINGS,
                ),
                phase="initial",
                specs=catalog.specs,
                input_messages=_initial_input_transcript(instructions, user_prompt),
                provider_error_type=ModelAPIError,
            )
            decision = (
                _resolve_final_response(result.output, request.context_id)
                if final_ready
                else _resolve_deferred(result.output, catalog, request.context_id)
            )
            if decision is None and not final_ready:
                repair = _repair_input(
                    result.output,
                    catalog,
                    DeferredToolRequests,
                    DeferredToolResults,
                    ModelRetry,
                    request.context_id,
                )
                repair_kwargs = (
                    {"deferred_tool_results": repair}
                    if isinstance(repair, DeferredToolResults)
                    else {"user_prompt": repair}
                )
                repair_history = result.all_messages()
                repair_transcript = _repair_input_transcript(result, repair_kwargs)
                result = await self._run_provider_call(
                    lambda: agent.run(
                        message_history=repair_history,
                        toolsets=[toolset],
                        usage=usage,
                        usage_limits=limits,
                        model_settings=_ACTION_MODEL_SETTINGS,
                        **repair_kwargs,
                    ),
                    phase="tool_call_repair",
                    specs=catalog.specs,
                    input_messages=repair_transcript,
                    provider_error_type=ModelAPIError,
                )
                decision = _resolve_deferred(result.output, catalog, request.context_id)
            if decision is None:
                return self._invocation_failure(
                    _failure(
                        ModelFailureKind.SCHEMA_ERROR,
                        "model did not produce one valid current tool call after bounded repair",
                    ),
                    request,
                )
        except asyncio.CancelledError:
            self._invocation_failure(
                _failure(ModelFailureKind.TIMEOUT, "model invocation was cancelled"),
                request,
            )
            raise
        except UsageLimitExceeded:
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.SCHEMA_ERROR,
                    "model exceeded the bounded decision repair allowance",
                ),
                request,
            )
        except UnexpectedModelBehavior as error:
            self._record_local_failure(error, "pydantic_ai_output_validation", catalog.specs)
            return self._invocation_failure(
                _failure(ModelFailureKind.SCHEMA_ERROR, "model tool response violated the grounded contract"),
                request,
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
            )
        except (GroundedToolResolutionError, ValueError, TypeError):
            return self._invocation_failure(
                _failure(ModelFailureKind.SCHEMA_ERROR, "grounded tool response could not be resolved"),
                request,
            )
        except Exception as error:
            self._record_local_failure(error, "local_runtime", catalog.specs)
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.INTERNAL_ERROR,
                    "PydanticAI decision adapter failed locally",
                ),
                request,
            )

        run_usage = result.usage
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
            prompt_version=self.context_binder.prompts.version,
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            latency_ms=(time.perf_counter() - semantic_started) * 1000,
            prompt_tokens=run_usage.input_tokens,
            completion_tokens=run_usage.output_tokens,
            total_tokens=run_usage.input_tokens + run_usage.output_tokens,
            rate_limit_retry_count=rate_limit_retries,
            transient_retry_count=max(0, self.last_provider_retry_count - rate_limit_retries),
            grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
            perception_profile=self.perception_profile.value,
            endpoint_host=self.endpoint_host,
        )
        invocation = ModelInvocationResult(
            output=ResolvedModelDecision(decision, metadata),
            metadata=metadata,
            attempts=self.last_generation_attempts,
            repair_diagnostics=self._repair_diagnostics(),
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _invocation_failure(
        self,
        failure: ModelFailure,
        request: ModelDecisionRequest,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            attempts=self.last_generation_attempts,
            repair_diagnostics=self._repair_diagnostics(),
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _lineage(self, request: ModelDecisionRequest) -> Mapping[str, object]:
        return {
            "role": "ActionPolicy",
            "adapter": "pydantic-ai",
            "request_id": request.request_id,
            "context_id": request.context_id,
        }

    def _repair_diagnostics(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            {
                "kind": "tool_call_repair",
                "phase": item.phase,
                "status": item.status,
            }
            for item in self.last_generation_attempts
            if item.phase == "tool_call_repair"
        )

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
            "tool_argument_repair_count": sum(
                1 for item in self.last_generation_attempts if item.phase == "tool_call_repair"
            ),
        }

    async def _run_provider_call(
        self,
        call,
        *,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        provider_error_type: type[Exception],
    ) -> object:
        for retry_index in range(_MAX_PROVIDER_RETRIES + 1):
            attempt_phase = phase if retry_index == 0 else f"{phase}_provider_retry"
            if retry_index:
                object.__setattr__(
                    self,
                    "last_provider_retry_count",
                    self.last_provider_retry_count + 1,
                )
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            started = time.perf_counter()
            try:
                result = await call()
            except asyncio.CancelledError:
                self._record_cancelled_attempt(
                    attempt_phase,
                    specs,
                    input_messages,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                raise
            except provider_error_type as error:
                detail = _classify_provider_failure(error)
                self._record_provider_failure(
                    detail,
                    attempt_phase,
                    specs,
                    input_messages,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                if retry_index >= _MAX_PROVIDER_RETRIES or not detail.retryable:
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
                specs,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            return result
        raise AssertionError("bounded provider retry loop did not resolve")

    def _record_generation(
        self,
        result: object,
        phase: str,
        specs: tuple[object, ...],
        *,
        latency_ms: float = 0.0,
    ) -> None:
        messages = json.loads(result.new_messages_json())
        requests = [message for message in messages if message.get("kind") == "request"]
        responses = [message for message in messages if message.get("kind") == "response"]
        usage = result.usage
        response = responses[-1] if responses else {}
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": requests,
            "llm.output_messages": responses,
            "llm.tools": [
                {
                    "tool.name": getattr(spec, "name", ""),
                    "tool.description": getattr(spec, "description", ""),
                    "tool.json_schema": to_json_compatible(getattr(spec, "input_schema", {})),
                }
                for spec in specs
            ],
            "llm.token_count.prompt": usage.input_tokens,
            "llm.token_count.completion": usage.output_tokens,
            "llm.token_count.total": usage.input_tokens + usage.output_tokens,
            "response.id": str(response.get("provider_response_id") or ""),
            "status": "accepted",
            "error": "",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="accepted",
            response_id=str(response.get("provider_response_id") or ""),
            latency_ms=latency_ms,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _record_cancelled_attempt(
        self,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        *,
        latency_ms: float,
    ) -> None:
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": input_messages,
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(specs),
            "status": "cancelled",
            "network_dispatched": True,
            "error.code": "cancelled",
            "error.exception_class": "CancelledError",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="cancelled",
            latency_ms=latency_ms,
            exception_class="CancelledError",
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _record_provider_failure(
        self,
        detail: _ProviderFailureDetail,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        *,
        latency_ms: float,
    ) -> None:
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": input_messages,
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(specs),
            "status": "failed",
            "error.code": detail.code.value,
            "error.reason": detail.reason,
            "error.exception_class": detail.exception_class,
            "error.http_status": detail.status_code,
            "error.retryable": detail.retryable,
            "error.retry_after_s": detail.retry_after_s,
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="failed",
            latency_ms=latency_ms,
            exception_class=detail.exception_class,
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _record_local_failure(
        self,
        error: Exception,
        phase: str,
        specs: tuple[object, ...],
    ) -> None:
        if self.last_generation_attempts and self.last_generation_attempts[-1].status == "failed":
            return
        detail = _ProviderFailureDetail(
            ProviderFailureCode.UNAVAILABLE,
            False,
            str(error)[:500] or "PydanticAI decision adapter failed locally",
            type(error).__name__,
        )
        self._record_provider_failure(detail, phase, specs, (), latency_ms=0.0)


def zhipu_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Build the PydanticAI policy for Zhipu or Aliyun OpenAI-compatible endpoints."""

    if not 1 < call_timeout_s <= 300:
        raise ValueError("PydanticAI policy timeout must be in (1, 300]")
    try:
        from openai import AsyncOpenAI
        from pydantic_ai.models.zai import ZaiModel
        from pydantic_ai.providers.zai import ZaiProvider
    except ImportError as exc:
        raise RuntimeError("install the pydantic-ai project extra") from exc

    env = os.environ if environment is None else environment
    profile = env.get("LLM_ACTIVE_PROFILE", "").strip().casefold()
    if profile not in {"zhipu", "aliyun"}:
        raise ValueError("PydanticAI model adapter supports only zhipu or aliyun profiles")
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("PydanticAI model adapter forbids provider fallback")
    prefix = "LLM_ZHIPU" if profile == "zhipu" else "LLM_ALIYUN"
    base_url = _required(env, f"{prefix}_BASE_URL")
    api_key = _required(env, f"{prefix}_API_KEY")
    model_id = _required(env, f"{prefix}_MODEL")
    if model_id.casefold() == "glm-4.1v-thinking-flashx":
        raise ValueError("glm-4.1v-thinking-flashx requires LLM_MODEL_ADAPTER=compact-json")
    selected_perception = DecisionPerceptionProfile(
        perception_profile
        or env.get("LLM_DECISION_PERCEPTION", DecisionPerceptionProfile.TEXT_ONLY.value)
    )
    retry_delay_budget_s = min(_MAX_PROVIDER_BACKOFF_S, max(0.1, call_timeout_s * 0.1))
    transport_timeout_s = (call_timeout_s - retry_delay_budget_s - 0.5) / 2
    if transport_timeout_s <= 0:
        raise ValueError("PydanticAI policy timeout cannot fit bounded provider recovery")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=transport_timeout_s,
        max_retries=0,
    )
    model = ZaiModel(model_id, provider=ZaiProvider(openai_client=client))
    port = PydanticAIGroundedDecisionPort(
        model=model,
        provider_id=profile,
        model_id=model_id,
        endpoint_host=_endpoint_host(base_url),
        supports_multimodal=profile == "zhipu" and _zhipu_supports_multimodal(model_id),
        perception_profile=selected_perception,
        transport_timeout_s=transport_timeout_s,
        provider_retry_backoff_s=min(_DEFAULT_PROVIDER_BACKOFF_S, retry_delay_budget_s),
        max_provider_retry_delay_s=retry_delay_budget_s,
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=call_timeout_s)


def _endpoint_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return (parsed.netloc or parsed.path.split("/", 1)[0]).strip().casefold()


def _resolve_deferred(output, catalog, context_id: str):
    from pydantic_ai import DeferredToolRequests

    if not isinstance(output, DeferredToolRequests) or output.approvals or len(output.calls) != 1:
        return None
    call = output.calls[0]
    try:
        arguments = call.args_as_dict(raise_if_invalid=True)
        reconciliation = ProviderCallNormalizer().normalize(
            ToolCall(call.tool_name, arguments, call.tool_call_id),
            catalog,
        )
        if reconciliation.status is not ToolCallReconciliationStatus.EXACT:
            return None
        assert reconciliation.exact_call is not None
        return resolve_grounded_action_call(
            catalog,
            reconciliation.exact_call,
            expected_context_id=context_id,
            expected_catalog_id=catalog.catalog_id,
        ).decision
    except (GroundedToolResolutionError, ValueError, TypeError):
        return None


def _final_response_ready(context) -> bool:
    if "final_response" in context.runtime_controls:
        return context.task.requested_output_ids.total_count > 0
    if "yield_subtask" in context.runtime_controls:
        return False
    requested = context.task.requested_output_ids
    confirmed = {item.output_id for item in context.task.evaluation.outputs}
    return (
        context.task.evaluation.status == "complete"
        and requested.total_count > 0
        and not requested.truncated
        and all(item in confirmed for item in requested.items)
    )


def _resolve_final_response(output, context_id: str) -> FinalResponse | None:
    if not isinstance(output, str):
        return None
    try:
        return FinalResponse(context_id, output)
    except ValueError:
        return None


def _repair_input(output, catalog, deferred_type, deferred_results_type, model_retry_type, context_id: str):
    message = _repair_message(output, catalog, deferred_type, context_id)
    if isinstance(output, deferred_type) and output.calls:
        return deferred_results_type(
            calls={call.tool_call_id: model_retry_type(message) for call in output.calls}
        )
    return message


def _repair_message(output, catalog, deferred_type, context_id: str) -> str:
    if isinstance(output, deferred_type) and len(output.calls) == 1:
        call = output.calls[0]
        spec = next((item for item in catalog.specs if item.name == call.tool_name), None)
        if spec is not None:
            schema = json.dumps(
                to_json_compatible(spec.input_schema),
                separators=(",", ":"),
                ensure_ascii=False,
            )
            guidance = ""
            try:
                reconciliation = ProviderCallNormalizer().normalize(
                    ToolCall(
                        call.tool_name,
                        call.args_as_dict(raise_if_invalid=True),
                        call.tool_call_id,
                    ),
                    catalog,
                )
                if reconciliation.did_you_mean:
                    candidates = [
                        {
                            "tool": candidate.tool_name,
                            "arguments": to_json_compatible(candidate.public_arguments),
                        }
                        for candidate in reconciliation.did_you_mean[:3]
                    ]
                    guidance = (
                        " Candidate corrections: "
                        + json.dumps(candidates, separators=(",", ":"), ensure_ascii=False)
                        + "."
                    )
                elif reconciliation.status is ToolCallReconciliationStatus.EXACT:
                    assert reconciliation.exact_call is not None
                    try:
                        resolve_grounded_action_call(
                            catalog,
                            reconciliation.exact_call,
                            expected_context_id=context_id,
                            expected_catalog_id=catalog.catalog_id,
                        )
                    except GroundedToolResolutionError as exc:
                        guidance = f" Runtime rejection: {str(exc)}."
            except (ValueError, TypeError):
                pass
            return (
                f"Invalid arguments for {spec.name}. Re-emit exactly one call using this schema: "
                f"{schema}.{guidance}"
            )
    names = ", ".join(spec.name for spec in catalog.specs)
    return f"Emit exactly one current tool call. Available tools: {names}"


def _pydantic_prompt(messages, image_inputs: Sequence[AgentImageInput], binary_content_type):
    if len(messages) != 2 or messages[0].role != "system" or messages[1].role != "user":
        raise ValueError("grounded PydanticAI prompt requires one system and one user message")
    instructions = messages[0].content
    if not isinstance(instructions, str):
        raise ValueError("grounded PydanticAI instructions must be text")
    content = messages[1].content
    if isinstance(content, str):
        return instructions, content
    text_parts = [part.text for part in content if part.type == "text"]
    if len(text_parts) != 1:
        raise ValueError("grounded PydanticAI prompt requires one public text projection")
    prompt: list[object] = [text_parts[0]]
    prompt.extend(
        binary_content_type(data=image.data, media_type=image.mime_type)
        for image in image_inputs
    )
    return instructions, prompt


def _initial_input_transcript(instructions: str, user_prompt: object) -> list[dict[str, object]]:
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": _safe_prompt_projection(user_prompt)},
    ]


def _repair_input_transcript(result: object, repair_kwargs: Mapping[str, object]) -> object:
    try:
        history = json.loads(result.all_messages_json())
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        history = [{"history": "retained_by_pydantic_ai"}]
    repair = repair_kwargs.get("user_prompt") or repair_kwargs.get("deferred_tool_results")
    return [*history, {"role": "repair", "content": _safe_prompt_projection(repair)}]


def _safe_prompt_projection(value: object) -> object:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        projected = []
        for item in value:
            data = getattr(item, "data", None)
            if isinstance(data, (bytes, bytearray)):
                projected.append(
                    {
                        "type": "binary",
                        "media_type": str(getattr(item, "media_type", "")),
                        "byte_count": len(data),
                    }
                )
            else:
                projected.append(to_json_compatible(item))
        return projected
    try:
        return to_json_compatible(value)
    except (TypeError, ValueError):
        return {"type": type(value).__name__}


def _tool_transcript(specs: tuple[object, ...]) -> list[dict[str, object]]:
    return [
        {
            "tool.name": getattr(spec, "name", ""),
            "tool.description": getattr(spec, "description", ""),
            "tool.json_schema": to_json_compatible(getattr(spec, "input_schema", {})),
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
) -> ModelFailure:
    return ModelFailure(
        kind,
        reason,
        retryable,
        provider_code,
        retry_after_s,
        attempt_origin=ProviderAttemptOrigin.NETWORK,
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
    "zhipu_pydantic_ai_policy_from_environment",
]
