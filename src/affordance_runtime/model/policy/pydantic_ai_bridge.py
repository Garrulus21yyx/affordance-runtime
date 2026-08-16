"""PydanticAI bridge for one fresh-world grounded GUI decision.

PydanticAI owns provider adaptation, tool-call parsing, and call IDs.  Tools are
external/deferred because the GUI Runtime remains the only owner of binding,
execution, risk, observation, and evaluation.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from affordance_runtime.agent.context.context import AgentImageInput
from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
)
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
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


@dataclass(frozen=True)
class PydanticAIGroundedDecisionPort:
    """Resolve exactly one current external tool call into a Runtime decision."""

    model: object
    provider_id: str
    model_id: str
    supports_multimodal: bool
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    transport_timeout_s: float = 85.0
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip():
            raise ValueError("PydanticAI model identity is required")
        if not 0 < self.transport_timeout_s <= 300:
            raise ValueError("PydanticAI transport timeout must be in (0, 300]")
        object.__setattr__(self, "perception_profile", DecisionPerceptionProfile(self.perception_profile))

    @property
    def requires_serialized_context(self) -> bool:
        return False

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
                self.perception_profile.value,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedModelDecision | ModelFailure:
        if request.agent_context is None:
            return _failure(ModelFailureKind.INTERNAL_ERROR, "grounded PydanticAI request lacks AgentContext")
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
            return _failure(
                ModelFailureKind.INTERNAL_ERROR,
                "PydanticAI optional dependency is not installed",
            )

        try:
            catalog = compile_grounded_action_catalog(request.agent_context)
            messages = self.context_binder.action_messages(
                request.agent_context,
                catalog.specs,
                request,
                supports_multimodal=self.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=False,
            )
            instructions, user_prompt = _pydantic_prompt(messages, request.image_inputs, BinaryContent)
            final_ready = _final_response_ready(request.agent_context)
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
            limits = UsageLimits(request_limit=2)
            result = await agent.run(
                user_prompt,
                toolsets=[] if final_ready else [toolset],
                usage=usage,
                usage_limits=limits,
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
                )
                repair_kwargs = (
                    {"deferred_tool_results": repair}
                    if isinstance(repair, DeferredToolResults)
                    else {"user_prompt": repair}
                )
                result = await agent.run(
                    message_history=result.all_messages(),
                    toolsets=[toolset],
                    usage=usage,
                    usage_limits=limits,
                    **repair_kwargs,
                )
                decision = _resolve_deferred(result.output, catalog, request.context_id)
            if decision is None:
                return _failure(
                    ModelFailureKind.SCHEMA_ERROR,
                    "model did not produce one valid current tool call after bounded repair",
                )
        except UsageLimitExceeded:
            return _failure(
                ModelFailureKind.SCHEMA_ERROR,
                "model exceeded the bounded decision repair allowance",
            )
        except UnexpectedModelBehavior:
            return _failure(ModelFailureKind.SCHEMA_ERROR, "model tool response violated the grounded contract")
        except ModelAPIError:
            return _failure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "PydanticAI model provider is unavailable",
                retryable=True,
            )
        except (GroundedToolResolutionError, ValueError, TypeError):
            return _failure(ModelFailureKind.SCHEMA_ERROR, "grounded tool response could not be resolved")
        except Exception:
            return _failure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "PydanticAI decision request failed",
                retryable=True,
            )

        run_usage = result.usage
        return ResolvedModelDecision(
            decision,
            ModelMetadata(
                provider_id=self.provider_id,
                model_id=self.model_id,
                endpoint_class="openai-compatible",
                prompt_version=self.context_binder.prompts.version,
                schema_version=request.schema_version,
                prompt_tokens=run_usage.input_tokens,
                completion_tokens=run_usage.output_tokens,
                total_tokens=run_usage.input_tokens + run_usage.output_tokens,
                grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
                perception_profile=self.perception_profile.value,
            ),
        )


def zhipu_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Build the PydanticAI policy for Zhipu's OpenAI-compatible endpoint."""

    if not 1 < call_timeout_s <= 300:
        raise ValueError("PydanticAI policy timeout must be in (1, 300]")
    try:
        from openai import AsyncOpenAI
        from pydantic_ai.models.zai import ZaiModel
        from pydantic_ai.providers.zai import ZaiProvider
    except ImportError as exc:
        raise RuntimeError("install the pydantic-ai project extra") from exc

    env = os.environ if environment is None else environment
    if env.get("LLM_ACTIVE_PROFILE", "").strip().casefold() != "zhipu":
        raise ValueError("PydanticAI model adapter currently supports only the zhipu profile")
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("PydanticAI model adapter forbids provider fallback")
    base_url = _required(env, "LLM_ZHIPU_BASE_URL")
    api_key = _required(env, "LLM_ZHIPU_API_KEY")
    model_id = _required(env, "LLM_ZHIPU_MODEL")
    if model_id.casefold() == "glm-4.1v-thinking-flashx":
        raise ValueError("glm-4.1v-thinking-flashx requires LLM_MODEL_ADAPTER=compact-json")
    selected_perception = DecisionPerceptionProfile(
        perception_profile
        or env.get("LLM_DECISION_PERCEPTION", DecisionPerceptionProfile.TEXT_ONLY.value)
    )
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=call_timeout_s - 1,
        max_retries=0,
    )
    model = ZaiModel(model_id, provider=ZaiProvider(openai_client=client))
    port = PydanticAIGroundedDecisionPort(
        model=model,
        provider_id="zhipu",
        model_id=model_id,
        supports_multimodal=_zhipu_supports_multimodal(model_id),
        perception_profile=selected_perception,
        transport_timeout_s=call_timeout_s - 0.5,
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=call_timeout_s)


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
    requested = context.task.requested_output_ids
    unresolved = context.progress.unresolved_outputs
    return (
        context.progress.validated_task_status == "complete"
        and requested.total_count > 0
        and not requested.truncated
        and unresolved.total_count == 0
    )


def _resolve_final_response(output, context_id: str) -> FinalResponse | None:
    if not isinstance(output, str):
        return None
    try:
        return FinalResponse(context_id, output)
    except ValueError:
        return None


def _repair_input(output, catalog, deferred_type, deferred_results_type, model_retry_type):
    message = _repair_message(output, catalog, deferred_type)
    if isinstance(output, deferred_type) and output.calls:
        return deferred_results_type(
            calls={call.tool_call_id: model_retry_type(message) for call in output.calls}
        )
    return message


def _repair_message(output, catalog, deferred_type) -> str:
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


def _failure(kind: ModelFailureKind, reason: str, *, retryable: bool = False) -> ModelFailure:
    return ModelFailure(
        kind,
        reason,
        retryable,
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
