"""Canonical immutable request authority at the PydanticAI model boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.agent.context.budgets import ModelRequestBudget
from affordance_runtime.agent.context.model_turn_delivery import DeliveredMedia, ModelTurnDelivery
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog
from affordance_runtime.model.policy.reasoning_policy import ActionPolicyCallProfile

CANONICAL_ENVELOPE_VERSION = "pydantic-ai-model-boundary.v1"
DETERMINISTIC_COUNTING_METHOD = "deterministic-conservative-v1"


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
    operand_roles: tuple[tuple[str, tuple[str, ...]], ...]
    route_deltas: tuple[tuple[str, str, str], ...]
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
        roles = tuple((ref, tuple(values)) for ref, values in self.operand_roles)
        routes = tuple(tuple(item) for item in self.route_deltas)
        if (
            tuple(ref for ref, _bbox in self.marks) != tuple(ref for ref, _values in roles)
            or any(set(values).difference({"source", "destination"}) for _ref, values in roles)
            or any(len(item) != 3 or not item[0] or not item[1] for item in routes)
        ):
            raise ValueError("canonical media route/operand-role relation is invalid")
        role_map = {ref: frozenset(values) for ref, values in roles}
        for ref, values in roles:
            expected = {
                role
                for _operation, source, destination in routes
                for role, operand in (("source", source), ("destination", destination))
                if operand == ref
            }
            if set(values) != expected:
                raise ValueError("canonical media operand roles differ from route deltas")
        if any(
            "source" not in role_map.get(source, frozenset())
            or (destination and "destination" not in role_map.get(destination, frozenset()))
            for _operation, source, destination in routes
        ):
            raise ValueError("canonical media route lacks its actual operand marks")
        object.__setattr__(self, "operand_roles", roles)
        object.__setattr__(self, "route_deltas", routes)


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
        if self.history_messages:
            raise ValueError("ActionPolicy history must be embedded in canonical user text")
        if not self.user_text:
            raise ValueError("canonical provider envelope user text is empty")
        if self.parallel_tool_calls or self.model_settings.get("parallel_tool_calls") is not False:
            raise ValueError("ActionPolicy canonical envelope must disable parallel tool calls")
        if self.output_token_reserve < 0 or self.counting_method != DETERMINISTIC_COUNTING_METHOD:
            raise ValueError("canonical provider envelope counting contract is invalid")
        if self.catalog.context_id != self.context_id or self.catalog.delivery_id != self.delivery_id:
            raise ValueError("canonical provider envelope catalog is stale")
        if tuple(item.name for item in self.function_tools) != tuple(item.spec.name for item in self.catalog.tools):
            raise ValueError("canonical provider envelope tool order differs from Catalog")
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "history_messages", tuple(freeze_json(item) for item in self.history_messages))
        object.__setattr__(self, "media", tuple(self.media))
        object.__setattr__(self, "function_tools", tuple(self.function_tools))
        object.__setattr__(self, "model_settings", freeze_json(self.model_settings))
        expected = _envelope_id(self.physical_content())
        if self.envelope_id != expected:
            raise ValueError("canonical provider envelope digest does not match physical content")

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
        return ({"kind": "request", "parts": ({"part_kind": "user-prompt", "content": user_parts},)},)

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
                {
                    "kind": "request",
                    "parts": (
                        {"part_kind": "user-prompt", "content": self.user_text},
                        *(
                            {
                                "part_kind": "binary",
                                "mime_type": item.mime_type,
                                "digest": item.digest,
                                "dimensions": item.dimensions,
                                "variant": item.variant,
                                "marks": item.marks,
                                "operand_roles": item.operand_roles,
                                "route_deltas": item.route_deltas,
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
            "messages": self.ordered_message_projection,
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
        attempt_phase: str | None = None,
    ) -> CanonicalProviderEnvelope:
        if delivery.context_id != request.context_id or catalog.delivery_id != delivery.delivery_id:
            raise ValueError("canonical provider envelope inputs are not current siblings")
        sections = self.context_binder._public_context_sections(  # noqa: SLF001 - delegated public projection owner
            request.agent_context,
            bool(delivery.media),
            delivery,
        )
        user_text = json.dumps(sections["public"], separators=(",", ":"), ensure_ascii=False)
        return self._create(
            request,
            delivery,
            catalog,
            identity=identity,
            instructions=(self.context_binder.prompts.actor,),
            user_text=user_text,
            call_profile=call_profile,
            output_token_reserve=output_token_reserve,
            attempt_phase=attempt_phase or call_profile.phase.value,
        )

    def bind_representation_repair(
        self,
        base: CanonicalProviderEnvelope,
        *,
        user_text: str,
        call_profile: ActionPolicyCallProfile,
        output_token_reserve: int,
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
            attempt_phase=call_profile.phase.value,
            diagnostics=base,
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
        attempt_phase: str,
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
        attempt_phase: str,
        diagnostics: object,
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
        }
        if identity.provider_id in {"zhipu", "aliyun"}:
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
        values = dict(
            context_id=context_id,
            delivery_id=delivery_id,
            identity=identity,
            instructions=instructions,
            user_text=user_text,
            history_messages=(),
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
        operand_roles=tuple(
            (mark.ref, tuple(role.value for role in mark.operand_roles))
            for mark in item.actual_marks
        ),
        route_deltas=tuple(
            (route.operation, route.source_ref, route.destination_ref)
            for route in item.route_deltas
        ),
        coordinate_space_lineage=item.coordinate_space_id,
    )


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
]
