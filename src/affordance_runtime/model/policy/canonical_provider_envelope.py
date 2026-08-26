"""Canonical immutable request authority at the PydanticAI model boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.agent.context.budgets import ModelRequestBudget
from affordance_runtime.agent.context.model_turn_delivery import DeliveredMedia, ModelTurnDelivery
from affordance_runtime.immutable import freeze_json, thaw_json_at_external_boundary, to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog
from affordance_runtime.model.policy.reasoning_policy import ActionPolicyCallProfile
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

CANONICAL_ENVELOPE_VERSION = "pydantic-ai-model-boundary.v1"
DETERMINISTIC_COUNTING_METHOD = "deterministic-conservative-v1"
UNEXECUTED_TOOL_CALL_MESSAGE = (
    "Not executed: the Runtime executes one tool call per fresh World. "
    "Reassess this exact proposal against the current World and call it again if it is still needed."
)


@dataclass(frozen=True)
class CanonicalProviderIdentity:
    provider_id: str
    model_id: str
    endpoint_host: str
    profile_id: str

    def __post_init__(self) -> None:
        if any(not item.strip() for item in (self.provider_id, self.model_id, self.endpoint_host, self.profile_id)):
            raise ValueError("canonical provider identity is incomplete")


@dataclass(frozen=True)
class CanonicalFunctionTool:
    name: str
    description: str
    parameters_json_schema: Mapping[str, object]
    strict: bool = True
    return_mode: str = "deferred"

    def __post_init__(self) -> None:
        if not self.name or not self.description or self.return_mode != "deferred":
            raise ValueError("canonical function tool is incomplete")
        object.__setattr__(self, "parameters_json_schema", freeze_json(self.parameters_json_schema))


@dataclass(frozen=True)
class CanonicalMediaRecord:
    data: bytes = field(repr=False)
    mime_type: str
    digest: str
    dimensions: tuple[int, int]
    variant: str
    marks: tuple[tuple[str, tuple[int, int, int, int]], ...]
    coordinate_space_lineage: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("canonical media requires exact bytes")
        if hashlib.sha256(self.data).hexdigest() != self.digest:
            raise ValueError("canonical media digest does not match bytes")
        if self.mime_type == "image/png" and not self.data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("canonical PNG media MIME does not match bytes")
        if self.mime_type == "image/jpeg" and not self.data.startswith(b"\xff\xd8\xff"):
            raise ValueError("canonical JPEG media MIME does not match bytes")
        if self.mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError("canonical media MIME is unsupported")
        if len(self.dimensions) != 2 or any(type(item) is not int or item <= 0 for item in self.dimensions):
            raise ValueError("canonical media dimensions are invalid")
        object.__setattr__(self, "marks", tuple((ref, tuple(box)) for ref, box in self.marks))
        if any(
            not PublicRefCodec.accepts(ref) or ref[:1] not in {PublicRefKind.EXECUTABLE.value, PublicRefKind.NODE.value}
            for ref, _bbox in self.marks
        ):
            raise ValueError("canonical media marks are invalid")


@dataclass(frozen=True)
class CanonicalOutputContract:
    output_mode: str = "text"
    allow_text_output: bool = True
    allow_image_output: bool = False
    output_tools: tuple[CanonicalFunctionTool, ...] = ()

    def __post_init__(self) -> None:
        if self.output_mode != "text" or not self.allow_text_output or self.allow_image_output:
            raise ValueError("unsupported ActionPolicy output contract")
        object.__setattr__(self, "output_tools", tuple(self.output_tools))


@dataclass(frozen=True)
class CanonicalProviderEnvelope:
    """The complete semantic request before PydanticAI performs typed conversion."""

    envelope_id: str
    context_id: str
    delivery_id: str
    identity: CanonicalProviderIdentity
    instructions: tuple[str, ...]
    user_text: str
    history_messages: tuple[Mapping[str, object], ...]
    pydantic_history: tuple[object, ...] = field(repr=False, compare=False, metadata={"serialize": False})
    tool_result: Mapping[str, object] | None
    tool_result_metadata: Mapping[str, object] = field(repr=False, compare=False)
    media: tuple[CanonicalMediaRecord, ...]
    function_tools: tuple[CanonicalFunctionTool, ...]
    model_settings: Mapping[str, object]
    parallel_tool_calls: bool
    output_contract: CanonicalOutputContract
    output_token_reserve: int
    counting_method: str
    attempt_phase: str
    attempt_trigger: str
    thinking_requested: str
    catalog: GroundedToolCatalog = field(repr=False, compare=False)
    delivery_projection: str = "full"
    expanded_region_count: int = 0
    folded_region_count: int = 0
    direct_action_count: int = 0
    searchable_action_count: int = 0
    obligation_group_count: int = 0
    admitted_record_count: int = 0
    available_record_count: int = 0
    manifest_route_count: int = 0
    packing_backoff_count: int = 0

    def __post_init__(self) -> None:
        if not self.envelope_id.startswith("provider-envelope:"):
            raise ValueError("canonical provider envelope identity is invalid")
        if not self.context_id.startswith("context:") or not self.delivery_id.startswith("delivery:"):
            raise ValueError("canonical provider envelope lineage is invalid")
        if len(self.instructions) != 1 or not self.instructions[0].strip():
            raise ValueError("ActionPolicy canonical envelope requires exactly one instruction")
        if bool(self.history_messages) != bool(self.tool_result):
            raise ValueError("deferred tool result requires its bounded call history")
        if bool(self.pydantic_history) != bool(self.history_messages):
            raise ValueError("canonical history requires the exact admitted PydanticAI messages")
        if self.history_messages:
            try:
                if tuple(self.history_messages) != _project_pydantic_history(self.pydantic_history):
                    raise ValueError("canonical history projection differs from exact PydanticAI messages")
                response_message = self.history_messages[-1]
                prior_call = next(part for part in tuple(response_message["parts"]) if part["part_kind"] == "tool-call")
                current_result = self.tool_result
                assert current_result is not None
                valid_exchange = (
                    response_message["kind"] == "response"
                    and prior_call["part_kind"] == "tool-call"
                    and prior_call["tool_call_id"] == current_result["tool_call_id"]
                    and prior_call["tool_name"] == current_result["tool_name"]
                )
            except (AssertionError, IndexError, KeyError, TypeError, ValueError):
                valid_exchange = False
            if not valid_exchange:
                raise ValueError("deferred tool result does not match its prior call")
        if not self.user_text:
            raise ValueError("canonical provider envelope user text is empty")
        if self.parallel_tool_calls or self.model_settings.get("parallel_tool_calls") is not False:
            raise ValueError("ActionPolicy canonical envelope must disable parallel tool calls")
        if self.model_settings.get("tool_choice") != "auto":
            raise ValueError("ActionPolicy initial request must allow reasoning with one offered tool call")
        if self.output_token_reserve < 0 or self.counting_method != DETERMINISTIC_COUNTING_METHOD:
            raise ValueError("canonical provider envelope counting contract is invalid")
        if self.catalog.context_id != self.context_id or self.catalog.delivery_id != self.delivery_id:
            raise ValueError("canonical provider envelope catalog is stale")
        if tuple(item.name for item in self.function_tools) != tuple(item.spec.name for item in self.catalog.tools):
            raise ValueError("canonical provider envelope tool order differs from Catalog")
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "history_messages", tuple(freeze_json(item) for item in self.history_messages))
        object.__setattr__(self, "pydantic_history", tuple(self.pydantic_history))
        if self.tool_result is not None:
            object.__setattr__(self, "tool_result", freeze_json(self.tool_result))
        object.__setattr__(self, "tool_result_metadata", freeze_json(self.tool_result_metadata))
        if bool(self.tool_result) != bool(self.tool_result_metadata):
            raise ValueError("deferred public return and private metadata must be paired")
        object.__setattr__(self, "media", tuple(self.media))
        object.__setattr__(self, "function_tools", tuple(self.function_tools))
        object.__setattr__(self, "model_settings", freeze_json(self.model_settings))
        expected = _envelope_id(self.physical_content())
        if self.envelope_id != expected:
            raise ValueError("canonical provider envelope digest does not match physical content")

    @property
    def deferred_tool_returns(self) -> tuple[Mapping[str, object], ...]:
        """Project the executed result and native failures for unselected proposals."""

        if self.tool_result is None:
            return ()
        response = self.history_messages[-1]
        calls = tuple(part for part in tuple(response["parts"]) if part["part_kind"] == "tool-call")
        return (
            self.tool_result,
            *(
                {
                    "part_kind": "tool-return",
                    "tool_call_id": call["tool_call_id"],
                    "tool_name": call["tool_name"],
                    "return_value": UNEXECUTED_TOOL_CALL_MESSAGE,
                    "failed": True,
                    "outcome": "failed",
                }
                for call in calls[1:]
            ),
        )

    @property
    def ordered_message_projection(self) -> tuple[Mapping[str, object], ...]:
        user_parts: tuple[Mapping[str, object], ...] = (
            {"part_kind": "text", "content": self.user_text},
            *(
                {
                    "part_kind": "binary",
                    "media_type": item.mime_type,
                    "data": item.data,
                    "digest": item.digest,
                }
                for item in self.media
            ),
        )
        history: list[Mapping[str, object]] = list(self.history_messages)
        result_parts = tuple(
            {
                "part_kind": "tool-return",
                "tool_call_id": item["tool_call_id"],
                "tool_name": item["tool_name"],
                "content": thaw_json_at_external_boundary(item["return_value"]),
            }
            for item in self.deferred_tool_returns
        )
        current_parts: tuple[Mapping[str, object], ...] = (
            *result_parts,
            {"part_kind": "user-prompt", "content": user_parts},
        )
        return (*history, {"kind": "request", "parts": current_parts})

    def physical_content(self) -> Mapping[str, object]:
        """Stable physical semantics; excludes Runtime-only lineage and object identity."""

        return {
            "version": CANONICAL_ENVELOPE_VERSION,
            "identity": {
                "provider_id": self.identity.provider_id,
                "model_id": self.identity.model_id,
                "endpoint_host": self.identity.endpoint_host,
                "profile_id": self.identity.profile_id,
            },
            "instructions": self.instructions,
            "messages": (
                *self.history_messages,
                {
                    "kind": "request",
                    "parts": (
                        *self.deferred_tool_returns,
                        {"part_kind": "user-prompt", "content": self.user_text},
                        *(
                            {
                                "part_kind": "binary",
                                "mime_type": item.mime_type,
                                "digest": item.digest,
                                "dimensions": item.dimensions,
                                "variant": item.variant,
                                "marks": item.marks,
                            }
                            for item in self.media
                        ),
                    ),
                },
            ),
            "tools": tuple(
                {
                    "name": item.name,
                    "description": item.description,
                    "parameters_json_schema": to_json_compatible(item.parameters_json_schema),
                    "strict": item.strict,
                    "return_mode": item.return_mode,
                }
                for item in self.function_tools
            ),
            "model_settings": to_json_compatible(self.model_settings),
            "parallel_tool_calls": self.parallel_tool_calls,
            "output_contract": {
                "output_mode": self.output_contract.output_mode,
                "allow_text_output": self.output_contract.allow_text_output,
                "allow_image_output": self.output_contract.allow_image_output,
                "output_tools": tuple(
                    {
                        "name": item.name,
                        "description": item.description,
                        "parameters_json_schema": to_json_compatible(item.parameters_json_schema),
                        "strict": item.strict,
                    }
                    for item in self.output_contract.output_tools
                ),
            },
            "output_token_reserve": self.output_token_reserve,
        }

    def model_boundary_projection(self) -> Mapping[str, object]:
        """Normalization target for FunctionModel callback values."""

        return {
            "instructions": self.instructions,
            "messages": (
                *_project_pydantic_history(self.pydantic_history, include_binary_data=True),
                self.ordered_message_projection[-1],
            ),
            "function_tools": tuple(
                {
                    "name": item.name,
                    "description": item.description,
                    "parameters_json_schema": to_json_compatible(item.parameters_json_schema),
                    "strict": item.strict,
                }
                for item in self.function_tools
            ),
            "model_settings": to_json_compatible(self.model_settings),
            "output_mode": self.output_contract.output_mode,
            "allow_text_output": self.output_contract.allow_text_output,
            "allow_image_output": self.output_contract.allow_image_output,
            "output_tools": (),
        }


@dataclass(frozen=True)
class CanonicalProviderEnvelopeBinder:
    """Sole producer of complete ActionPolicy provider envelopes."""

    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    request_budget: ModelRequestBudget = field(default_factory=ModelRequestBudget)

    def bind(
        self,
        request: ModelDecisionRequest,
        delivery: ModelTurnDelivery,
        catalog: GroundedToolCatalog,
        *,
        identity: CanonicalProviderIdentity,
        call_profile: ActionPolicyCallProfile,
        output_token_reserve: int,
        request_timeout_s: float | None = None,
        attempt_phase: str | None = None,
        history_messages: tuple[object, ...] = (),
    ) -> CanonicalProviderEnvelope:
        if delivery.context_id != request.context_id or catalog.delivery_id != delivery.delivery_id:
            raise ValueError("canonical provider envelope inputs are not current siblings")
        sections = self.context_binder._public_context_sections(  # noqa: SLF001 - delegated public projection owner
            request.agent_context,
            bool(delivery.media),
            delivery,
        )
        # The first accepted SDK turn is later normalized into the sole
        # task/plan anchor.  Once that anchor exists, each new user turn owns
        # only the authoritative fresh World and ephemeral control feedback;
        # replaying TaskGoal and GoalPlan inside every historical World is both
        # redundant and attention-distorting.
        user_payload = sections["current_turn"] if history_messages else sections["public"]
        user_text = json.dumps(user_payload, separators=(",", ":"), ensure_ascii=False)
        return self._create(
            request,
            delivery,
            catalog,
            identity=identity,
            instructions=(self.context_binder.prompts.actor,),
            user_text=user_text,
            call_profile=call_profile,
            output_token_reserve=output_token_reserve,
            request_timeout_s=request_timeout_s,
            attempt_phase=attempt_phase or call_profile.phase.value,
            history_messages=history_messages,
        )

    def bind_representation_repair(
        self,
        base: CanonicalProviderEnvelope,
        *,
        user_text: str,
        call_profile: ActionPolicyCallProfile,
        output_token_reserve: int,
        request_timeout_s: float | None = None,
    ) -> CanonicalProviderEnvelope:
        instructions = (
            "Repair only the rejected tool-call representation. Emit exactly one offered tool call. "
            "Do not inspect the GUI, choose a new strategy, or change a valid target or operation.",
        )
        return self._create_from_parts(
            context_id=base.context_id,
            delivery_id=base.delivery_id,
            catalog=base.catalog,
            identity=base.identity,
            instructions=instructions,
            user_text=user_text,
            media=(),
            call_profile=call_profile,
            output_token_reserve=output_token_reserve,
            request_timeout_s=(
                request_timeout_s
                if request_timeout_s is not None
                else float(base.model_settings["timeout"])
                if "timeout" in base.model_settings
                else None
            ),
            attempt_phase=call_profile.phase.value,
            diagnostics=base,
            history_messages=(),
            tool_result=None,
        )

    def _create(
        self,
        request: ModelDecisionRequest,
        delivery: ModelTurnDelivery,
        catalog: GroundedToolCatalog,
        *,
        identity: CanonicalProviderIdentity,
        instructions: tuple[str, ...],
        user_text: str,
        call_profile: ActionPolicyCallProfile,
        output_token_reserve: int,
        request_timeout_s: float | None = None,
        attempt_phase: str,
        history_messages: tuple[object, ...],
    ) -> CanonicalProviderEnvelope:
        context = request.agent_context
        direct_refs = frozenset(delivery.manifest.executable_refs)
        searchable = sum(1 for option in context.complete_actions if option.target_ref not in direct_refs)
        return self._create_from_parts(
            context_id=request.context_id,
            delivery_id=delivery.delivery_id,
            catalog=catalog,
            identity=identity,
            instructions=instructions,
            user_text=user_text,
            media=tuple(_media_record(item) for item in delivery.media),
            call_profile=call_profile,
            output_token_reserve=output_token_reserve,
            request_timeout_s=request_timeout_s,
            attempt_phase=attempt_phase,
            diagnostics=(
                delivery.view.projection,
                int(delivery.view.coverage.get("expanded_regions", 0)),
                int(delivery.view.coverage.get("folded_regions", 0)),
                len(context.complete_actions) - searchable,
                searchable,
                len(context.action_delivery_plan.obligations),
                sum(dict(delivery.admitted_record_counts).values()),
                sum(len(item.remaining) for item in context.action_delivery_plan.obligations),
                len(delivery.manifest.action_routes),
                delivery.packing_backoff_count,
            ),
            history_messages=_project_pydantic_history(history_messages),
            pydantic_history=history_messages,
            tool_result=delivery.tool_result,
        )

    @staticmethod
    def _create_from_parts(
        *,
        context_id: str,
        delivery_id: str,
        catalog: GroundedToolCatalog,
        identity: CanonicalProviderIdentity,
        instructions: tuple[str, ...],
        user_text: str,
        media: tuple[CanonicalMediaRecord, ...],
        call_profile: ActionPolicyCallProfile,
        output_token_reserve: int,
        request_timeout_s: float | None = None,
        attempt_phase: str,
        diagnostics: object,
        history_messages: tuple[Mapping[str, object], ...],
        pydantic_history: tuple[object, ...] = (),
        tool_result: object | None,
        tool_result_metadata: Mapping[str, object] | None = None,
    ) -> CanonicalProviderEnvelope:
        tools = tuple(
            CanonicalFunctionTool(
                item.name,
                item.description,
                item.input_schema,
                strict=True,
            )
            for item in catalog.specs
        )
        settings = {
            "max_tokens": call_profile.max_output_tokens,
            "temperature": 0.0,
            "parallel_tool_calls": False,
            # The ordinary request must permit one response to carry the
            # provider's native optional text/reasoning and its tool call. The
            # PydanticAI output-retry boundary alone strengthens this to
            # ``required`` after a text-only provider violation.
            "tool_choice": "auto",
        }
        if request_timeout_s is not None:
            if request_timeout_s <= 0:
                raise ValueError("provider request timeout must be positive")
            settings["timeout"] = request_timeout_s
        if identity.provider_id in {"zhipu", "aliyun", "deepseek"}:
            settings["thinking"] = call_profile.thinking_mode == "enabled"
        output = CanonicalOutputContract()
        if isinstance(diagnostics, CanonicalProviderEnvelope):
            diagnostic_values = (
                diagnostics.delivery_projection,
                diagnostics.expanded_region_count,
                diagnostics.folded_region_count,
                diagnostics.direct_action_count,
                diagnostics.searchable_action_count,
                diagnostics.obligation_group_count,
                diagnostics.admitted_record_count,
                diagnostics.available_record_count,
                diagnostics.manifest_route_count,
                diagnostics.packing_backoff_count,
            )
        else:
            diagnostic_values = diagnostics
        public_tool_result = (
            dict(tool_result)
            if isinstance(tool_result, Mapping)
            else {
                "part_kind": "tool-return",
                "tool_call_id": tool_result.tool_call_id,
                "tool_name": tool_result.tool_name,
                "return_value": tool_result.return_value,
                "failed": tool_result.failed,
            }
            if tool_result is not None
            else None
        )
        private_tool_result_metadata = (
            dict(tool_result_metadata)
            if tool_result_metadata is not None
            else tool_result.metadata
            if tool_result is not None
            else {}
        )
        values = dict(
            context_id=context_id,
            delivery_id=delivery_id,
            identity=identity,
            instructions=instructions,
            user_text=user_text,
            history_messages=history_messages,
            pydantic_history=pydantic_history,
            tool_result=public_tool_result,
            tool_result_metadata=private_tool_result_metadata,
            media=media,
            function_tools=tools,
            model_settings=settings,
            parallel_tool_calls=False,
            output_contract=output,
            output_token_reserve=output_token_reserve,
            counting_method=DETERMINISTIC_COUNTING_METHOD,
            attempt_phase=attempt_phase,
            attempt_trigger=call_profile.trigger.value,
            thinking_requested=call_profile.thinking_mode,
            catalog=catalog,
            delivery_projection=diagnostic_values[0],
            expanded_region_count=diagnostic_values[1],
            folded_region_count=diagnostic_values[2],
            direct_action_count=diagnostic_values[3],
            searchable_action_count=diagnostic_values[4],
            obligation_group_count=diagnostic_values[5],
            admitted_record_count=diagnostic_values[6],
            available_record_count=diagnostic_values[7],
            manifest_route_count=diagnostic_values[8],
            packing_backoff_count=diagnostic_values[9],
        )
        provisional = CanonicalProviderEnvelope.__new__(CanonicalProviderEnvelope)
        for key, value in values.items():
            object.__setattr__(provisional, key, value)
        envelope_id = _envelope_id(provisional.physical_content())
        return CanonicalProviderEnvelope(envelope_id=envelope_id, **values)


def _media_record(item: DeliveredMedia) -> CanonicalMediaRecord:
    return CanonicalMediaRecord(
        data=item.data,
        mime_type=item.mime_type,
        digest=item.sha256,
        dimensions=_image_dimensions(item.data),
        variant="marked" if item.actual_marks else "raw",
        marks=tuple((mark.ref, mark.bbox) for mark in item.actual_marks),
        coordinate_space_lineage=item.coordinate_space_id,
    )


def _project_pydantic_history(
    messages: tuple[object, ...],
    *,
    include_binary_data: bool = False,
) -> tuple[Mapping[str, object], ...]:
    """Project official history; raw media is present only at the model boundary."""

    if not messages:
        return ()
    try:
        from pydantic_ai import BinaryContent
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            SystemPromptPart,
            TextContent,
            TextPart,
            ThinkingPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )
    except ImportError as exc:  # pragma: no cover - guarded by the provider bridge
        raise ValueError("PydanticAI messages are unavailable") from exc
    projected: list[Mapping[str, object]] = []
    pending: tuple[tuple[str, str], ...] | None = None
    summary_seen = False
    task_anchor_seen = False
    for index, message in enumerate(messages):
        if isinstance(message, ModelResponse):
            if pending is not None:
                raise ValueError("compact PydanticAI history has consecutive tool-call responses")
            calls = tuple(part for part in message.parts if isinstance(part, ToolCallPart))
            call_ids = tuple(call.tool_call_id for call in calls)
            if (
                not calls
                or len(set(call_ids)) != len(call_ids)
                or any(not call_id for call_id in call_ids)
                or any(not isinstance(part, (TextPart, ThinkingPart, ToolCallPart)) for part in message.parts)
            ):
                raise ValueError("accepted PydanticAI response must retain unique tool calls")
            pending = tuple((call.tool_name, call.tool_call_id) for call in calls)
            response_parts: list[Mapping[str, object]] = []
            for part in message.parts:
                if isinstance(part, TextPart):
                    response_parts.append({"part_kind": "text", "content": part.content})
                    continue
                if isinstance(part, ThinkingPart):
                    response_parts.append(
                        {
                            "part_kind": "thinking",
                            "content": part.content,
                            "id": part.id,
                            "signature": part.signature,
                            "provider_name": part.provider_name,
                            "provider_details": to_json_compatible(part.provider_details),
                        }
                    )
                    continue
                response_parts.append(
                    {
                        "part_kind": "tool-call",
                        "tool_name": part.tool_name,
                        "arguments": to_json_compatible(part.args_as_dict()),
                        "tool_call_id": part.tool_call_id,
                    }
                )
            projected.append(
                {
                    "kind": "response",
                    "parts": tuple(response_parts),
                }
            )
            continue
        if not isinstance(message, ModelRequest):
            raise ValueError("compact PydanticAI history expected a tool-result request")
        summaries = tuple(part for part in message.parts if isinstance(part, SystemPromptPart))
        if summaries:
            if index != 0 or pending is not None or summary_seen or len(summaries) != 1 or len(message.parts) != 1:
                raise ValueError("compact PydanticAI history has an invalid summary position")
            summary_seen = True
            projected.append(
                {
                    "kind": "request",
                    "parts": (
                        {
                            "part_kind": "system-prompt",
                            "content": summaries[0].content,
                        },
                    ),
                }
            )
            continue
        prompts = tuple(part for part in message.parts if isinstance(part, UserPromptPart))
        returns = tuple(part for part in message.parts if isinstance(part, ToolReturnPart))
        returned_identities = tuple((returned.tool_name, returned.tool_call_id) for returned in returns)
        marked_anchor = bool((message.metadata or {}).get("affordance_runtime.task_anchor"))
        maximum_prompts = 2 if marked_anchor else 1
        if len(prompts) > maximum_prompts or len(message.parts) != len(prompts) + len(returns):
            raise ValueError("PydanticAI history request contains unsupported parts")
        if not prompts and not returns:
            raise ValueError("PydanticAI history request is empty")
        if returns:
            if (
                pending is None
                or len(returns) != len(pending)
                or len({item[1] for item in returned_identities}) != len(returned_identities)
                or set(returned_identities) != set(pending)
            ):
                raise ValueError("completed PydanticAI request must close every proposed tool call")
            pending = None
        else:
            if pending is not None:
                raise ValueError("PydanticAI history request omitted a pending tool result")
            if not prompts:
                raise ValueError("PydanticAI history request without results needs a prompt")
            if marked_anchor:
                if task_anchor_seen:
                    raise ValueError("compact PydanticAI history has multiple task anchors")
                if len(prompts) not in {1, 2}:
                    raise ValueError("compact PydanticAI history has an invalid task anchor")
                task_anchor_seen = True
            elif not task_anchor_seen:
                # Backward-compatible official histories and direct Harness
                # tests begin with one unmarked user request.  Production
                # histories mark the separate task anchor explicitly.
                task_anchor_seen = True
        request_parts: list[Mapping[str, object]] = []
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                content = part.content
                content_items = (content,) if isinstance(content, str) else tuple(content)
                projected_content: list[Mapping[str, object]] = []
                for item in content_items:
                    if isinstance(item, str):
                        projected_content.append({"part_kind": "text", "content": item})
                    elif isinstance(item, TextContent):
                        projected_content.append({"part_kind": "text", "content": item.content})
                    elif isinstance(item, BinaryContent):
                        binary_projection: dict[str, object] = {
                            "part_kind": "binary",
                            "media_type": item.media_type,
                            "digest": hashlib.sha256(item.data).hexdigest(),
                        }
                        if include_binary_data:
                            binary_projection["data"] = item.data
                        projected_content.append(binary_projection)
                    else:
                        raise ValueError("PydanticAI history contains unsupported user content")
                request_parts.append(
                    {
                        "part_kind": "user-prompt",
                        "content": tuple(projected_content),
                    }
                )
                continue
            request_parts.append(
                {
                    "part_kind": "tool-return",
                    "tool_name": part.tool_name,
                    "tool_call_id": part.tool_call_id,
                    "content": to_json_compatible(part.content),
                    "metadata": to_json_compatible(part.metadata),
                    "outcome": part.outcome,
                }
            )
        projected.append(
            {
                "kind": "request",
                "parts": tuple(request_parts),
            }
        )
    if pending is None:
        raise ValueError("compact PydanticAI history lost its unresolved suffix")
    return tuple(projected)


def _image_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            length = int.from_bytes(data[index : index + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                return int.from_bytes(data[index + 5 : index + 7], "big"), int.from_bytes(
                    data[index + 3 : index + 5], "big"
                )
            index += max(2, length)
    raise ValueError("canonical media dimensions are unavailable")


def _envelope_id(content: Mapping[str, object]) -> str:
    encoded = json.dumps(
        to_json_compatible(content),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"provider-envelope:{hashlib.sha256(encoded).hexdigest()}"


__all__ = [
    "CANONICAL_ENVELOPE_VERSION",
    "CanonicalFunctionTool",
    "CanonicalMediaRecord",
    "CanonicalOutputContract",
    "CanonicalProviderEnvelope",
    "CanonicalProviderEnvelopeBinder",
    "CanonicalProviderIdentity",
    "DETERMINISTIC_COUNTING_METHOD",
    "UNEXECUTED_TOOL_CALL_MESSAGE",
]
