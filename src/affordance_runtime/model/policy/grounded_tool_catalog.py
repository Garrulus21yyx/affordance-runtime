"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from affordance_runtime.actions.paging import PUBLIC_ACTION_LABEL_MAX_CHARS
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView, ActorWorldSnapshot
from affordance_runtime.agent.context.compact_world_renderer import (
    inspect_actor_world,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.model_turn_delivery import ModelTurnDelivery
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    FinalResponse,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    Wait,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_compiler import GroundedToolCompiler
from affordance_runtime.model.policy.grounded_tool_contracts import (
    MAX_GROUNDED_TOOL_COUNT,
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    RegisteredGroundedTool,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.world.observation_needs import ObservationPurpose
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind


class GroundedLocalToolName(StrEnum):
    """Closed non-ActionSpace vocabulary owned by the grounded ToolCatalog."""

    REQUEST_EVIDENCE = "request_evidence"
    COUNT_CHILDREN = "count_children"
    READ_REGION = "read_region"
    SEARCH_PAGE_CONTENT = "search_page_content"
    LIST_REGIONS = "list_regions"
    FIND_CONTROLS = "find_controls"
    SUBMIT_FINAL_RESPONSE = "submit_final_response"
    ASK_USER = "ask_user"
    WAIT = "wait"
    ABORT = "abort"


@dataclass(frozen=True)
class _FindControlsBinding:
    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        query = str(arguments["query"]).strip()
        return RequestActionPage(
            context_id,
            query,
            tool_call_id=tool_call_id,
        )


@dataclass(frozen=True)
class _EvidenceBinding:
    purposes: tuple[str, ...]
    subjects: Mapping[str, str]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        purpose = str(arguments["purpose"])
        subject_ref = str(arguments["subject"])
        evidence_property = str(arguments.get("property", ""))
        try:
            return RequestObservation(
                context_id,
                purpose,
                self.subjects[subject_ref],
                evidence_property,
                f"agent declared {purpose} evidence gap",
                tool_call_id=tool_call_id,
            )
        except (KeyError, ValueError) as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS,
                str(exc),
            ) from exc


@dataclass(frozen=True)
class _ControlBinding:
    kind: GroundedLocalToolName

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        if self.kind is GroundedLocalToolName.ASK_USER:
            requested_fields = arguments.get("requested_fields", ())
            if not isinstance(requested_fields, list | tuple):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            return AskUser(
                context_id,
                str(arguments["question"]),
                tuple(str(item) for item in requested_fields),
                tool_call_id,
            )
        if self.kind is GroundedLocalToolName.WAIT:
            return Wait(
                context_id,
                str(arguments["reason"]),
                5_000,
                tool_call_id,
            )
        if self.kind is GroundedLocalToolName.ABORT:
            return Abort(
                context_id,
                str(arguments["reason"]),
                str(arguments["category"]),
                tool_call_id,
            )
        if self.kind is GroundedLocalToolName.SUBMIT_FINAL_RESPONSE:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)


@dataclass(frozen=True)
class _FinalResponseBinding:
    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        del tool_call_id
        return FinalResponse(context_id, str(arguments["content"]))


@dataclass(frozen=True)
class _CountChildrenBinding:
    counts: Mapping[str, int]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        raw_refs = arguments["containers"]
        if not isinstance(raw_refs, list | tuple):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        container_refs = tuple(str(item) for item in raw_refs)
        if any(item not in self.counts for item in container_refs):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        counts = {item: self.counts[item] for item in container_refs}
        return ReadRegionResult(
            context_id,
            GroundedLocalToolName.COUNT_CHILDREN.value,
            {"containers": container_refs},
            {"counts": counts, "total": sum(counts.values())},
            tool_call_id,
        )


@dataclass(frozen=True)
class _WorldReadBinding:
    context: AgentContext
    kind: str
    admitted_region_refs: frozenset[str] = frozenset()

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision | GroundedActionResolution:
        observation, region_index = _current_world_read_authority(self.context)
        region_ref = ""
        query = ""
        page_cursor = str(arguments.get("cursor", "") or "")
        if self.kind == "region":
            tool_name = GroundedLocalToolName.READ_REGION.value
            action = "read_region"
            region_ref = str(arguments["region_ref"])
            if region_ref not in self.admitted_region_refs:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.GROUNDING_GAP,
                    "region reference is unavailable in the current delivery",
                )
        elif self.kind == "find":
            tool_name = GroundedLocalToolName.SEARCH_PAGE_CONTENT.value
            action = "find"
            query = str(arguments["query"]).strip()
        elif self.kind == "view_all":
            tool_name = GroundedLocalToolName.LIST_REGIONS.value
            action = "view_all"
        else:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)

        result = inspect_actor_world(
            self.context.actor_world,
            self.context.grounding,
            region_index=region_index,
            canonical_world=self.context.canonical_world,
            observation=observation,
            action=action,
            region_ref=region_ref,
            query=query,
            cursor=page_cursor,
            public_fact_bindings=self.context.private_fact_bindings,
            evidence_index=self.context.evidence_index,
        )
        public_arguments: Mapping[str, object]
        if tool_name == GroundedLocalToolName.READ_REGION.value:
            public_arguments = {"region_ref": region_ref, **({"cursor": page_cursor} if page_cursor else {})}
        elif tool_name == GroundedLocalToolName.SEARCH_PAGE_CONTENT.value:
            public_arguments = {"query": query, **({"cursor": page_cursor} if page_cursor else {})}
        else:
            public_arguments = {"cursor": page_cursor} if page_cursor else {}
        public_result = dict(inspect_outcome_public(result))
        result_type = (
            SearchPageContentResult
            if tool_name == GroundedLocalToolName.SEARCH_PAGE_CONTENT.value
            else ReadRegionResult
        )
        return GroundedActionResolution(
            result_type(
                context_id,
                tool_name,
                public_arguments,
                public_result,
                tool_call_id,
            ),
        )


def _current_world_read_authority(context: AgentContext):
    if context.current_observation is None or context.region_index is None:
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.CATALOG_INVALID,
            "World reading requires a current observation and region index",
        )
    return context.current_observation, context.region_index


def compile_grounded_tool_catalog(
    context: AgentContext,
    phase: GroundedToolPhase,
    delivery: ModelTurnDelivery,
) -> GroundedToolCatalog:
    if phase is not GroundedToolPhase.ACTION_SELECTION:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    if delivery.context_id != context.context_id:
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.STALE_CATALOG,
            "ModelTurnDelivery belongs to another Context",
        )
    if delivery.action_candidates.world_observation_id != getattr(
        context.current_observation,
        "observation_id",
        delivery.action_candidates.world_observation_id,
    ):
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.STALE_CATALOG,
            "ModelTurnDelivery belongs to another World",
        )
    registered: list[RegisteredGroundedTool] = []

    purposes: set[str] = set()
    for capability in context.actor_world.observation_capabilities:
        if _observation_tool_needed(context, capability):
            purposes.update(set(capability["purposes"]) & _AGENT_PURPOSES)
    if purposes:
        refs = {
            ref: subject
            for ref, subject in context.grounding.private_subject_bindings().items()
            if ref in delivery.manifest.exact_refs
        }
        subjects = {"current_world": "current_world", **refs}
        ordered_purposes = tuple(sorted(purposes))
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.REQUEST_EVIDENCE.value,
                    "Request missing current-world evidence; Runtime chooses how to obtain it.",
                    _evidence_request_schema(ordered_purposes, subjects),
                ),
                _EvidenceBinding(ordered_purposes, subjects),
            )
        )

    registered.extend(
        RegisteredGroundedTool(
            item.public_spec,
            item,
        )
        for item in GroundedToolCompiler().compile(
            context.complete_actions,
            context_id=context.context_id,
            admitted_routes=frozenset(
                (route.operation, route.source_ref, route.destination_ref) for route in delivery.manifest.action_routes
            ),
        )
    )

    child_counts = {
        ref: count
        for ref, count in _countable_child_groups(context.actor_world).items()
        if ref in delivery.manifest.exact_refs
    }
    if child_counts:
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.COUNT_CHILDREN.value,
                    "Count direct children in current complete repeated groups.",
                    _object_schema(
                        {
                            "containers": {
                                "type": "array",
                                "description": "all relevant repeated-group references from the current observation",
                                "items": {
                                    "type": "string",
                                    "enum": sorted(child_counts),
                                },
                                "minItems": 1,
                                "maxItems": len(child_counts),
                            }
                        },
                        ("containers",),
                    ),
                ),
                _CountChildrenBinding(child_counts),
            )
        )

    if delivery.manifest.region_refs:
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.READ_REGION.value,
                    "Open one known current PageMap region for readable content; no browser action.",
                    _object_schema(
                        {
                            "region_ref": {
                                "type": "string",
                                "description": "current PageMap R-ref returned by the World view or a read/search tool",
                                "pattern": PublicRefCodec.pattern(PublicRefKind.REGION),
                            },
                            "cursor": {
                                "type": "string",
                                "description": "optional next_cursor returned by this same tool",
                                "minLength": 1,
                                "maxLength": 512,
                            },
                        },
                        ("region_ref",),
                    ),
                ),
                _WorldReadBinding(context, "region", frozenset(delivery.manifest.region_refs)),
            )
        )
    registered.extend(
        (
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.SEARCH_PAGE_CONTENT.value,
                    "Locate an exact text substring in current readable records; returns bounded exact-match pages, not semantic retrieval or proof that a collection was fully reviewed; no browser action.",
                    _object_schema(
                        {
                            "query": {
                                "type": "string",
                                "description": "exact text substring to locate in current readable records",
                                "minLength": 1,
                                "maxLength": 120,
                            },
                            "cursor": {
                                "type": "string",
                                "description": "optional next_cursor returned by this same tool",
                                "minLength": 1,
                                "maxLength": 512,
                            },
                        },
                        ("query",),
                    ),
                ),
                _WorldReadBinding(context, "find"),
            ),
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.LIST_REGIONS.value,
                    "List current PageMap region records; no browser action.",
                    _object_schema(
                        {
                            "cursor": {
                                "type": "string",
                                "description": "optional next_cursor returned by this same tool",
                                "minLength": 1,
                                "maxLength": 512,
                            }
                        }
                    ),
                ),
                _WorldReadBinding(context, "view_all"),
            ),
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.FIND_CONTROLS.value,
                    "Find ranked legal controls in the complete current ActionSpace; never executes.",
                    _object_schema(
                        {
                            "query": {
                                "type": "string",
                                "description": "desired current control or action",
                                "minLength": 1,
                                "maxLength": PUBLIC_ACTION_LABEL_MAX_CHARS,
                            }
                        },
                        ("query",),
                    ),
                ),
                _FindControlsBinding(),
            ),
        )
    )
    registered.append(
        RegisteredGroundedTool(
            ToolSpec(
                GroundedLocalToolName.SUBMIT_FINAL_RESPONSE.value,
                _final_response_description(context.final_response_guidance),
                _object_schema(
                    {
                        "content": {
                            "type": "string",
                            "description": "complete final answer, JSON when the task contract requires JSON",
                            "minLength": 1,
                            "maxLength": 8000,
                        },
                    },
                    ("content",),
                ),
            ),
            _FinalResponseBinding(),
        )
    )

    registered.extend(
        (
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.ASK_USER.value,
                    "Ask for task information unavailable in the interface.",
                    _object_schema(
                        {
                            "question": {
                                "type": "string",
                                "description": "one clear question",
                                "minLength": 1,
                                "maxLength": 1000,
                            },
                            "requested_fields": {
                                "type": "array",
                                "description": "facts only the user can provide",
                                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                                "maxItems": 8,
                            },
                        },
                        ("question",),
                    ),
                ),
                _ControlBinding(GroundedLocalToolName.ASK_USER),
            ),
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.WAIT.value,
                    "Wait five seconds, then observe a fresh World.",
                    _object_schema(
                        {
                            "reason": {
                                "type": "string",
                                "description": "what is still loading or changing",
                                "minLength": 1,
                                "maxLength": 500,
                            },
                        },
                        ("reason",),
                    ),
                ),
                _ControlBinding(GroundedLocalToolName.WAIT),
            ),
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.ABORT.value,
                    "Stop when safe progress is impossible.",
                    _object_schema(
                        {
                            "reason": {
                                "type": "string",
                                "description": "brief explanation",
                                "minLength": 1,
                                "maxLength": 500,
                            },
                            "category": {
                                "type": "string",
                                "description": "stop category",
                                "enum": ["policy", "safety", "unsupported", "no_progress", "user_request"],
                            },
                        },
                        ("reason", "category"),
                    ),
                ),
                _ControlBinding(GroundedLocalToolName.ABORT),
            ),
        )
    )
    return _catalog_from_registrations(context, delivery, tuple(registered))


def _catalog_from_registrations(
    context: AgentContext,
    delivery: ModelTurnDelivery,
    registered: tuple[RegisteredGroundedTool, ...],
) -> GroundedToolCatalog:
    names = tuple(tool.spec.name for tool in registered)
    if len(names) != len(set(names)):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    specs = [tool.spec for tool in registered]
    if not specs:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)

    public_tools = tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in specs
    )
    encoded = json.dumps(public_tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded_bytes = len(encoded.encode())
    if len(specs) > MAX_GROUNDED_TOOL_COUNT:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    digest = hashlib.sha256(f"{context.context_id}\0{delivery.delivery_id}\0{encoded}".encode()).hexdigest()[:32]
    catalog_id = f"grounded-catalog:{digest}"
    return GroundedToolCatalog(
        catalog_id,
        context.context_id,
        delivery.delivery_id,
        delivery.manifest,
        context.region_index,
        registered,
        encoded_bytes,
    )


def compile_grounded_action_catalog(
    context: AgentContext,
    delivery: ModelTurnDelivery,
) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
    )


def _final_response_description(guidance: str) -> str:
    base = "Submit the complete final answer supported in the current agent context for native evaluation."
    return base if not guidance else f"{base} Output contract: {guidance}"


def resolve_grounded_tool_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_delivery_id: str,
    expected_catalog_id: str | None = None,
) -> GroundedActionResolution:
    if (
        catalog.context_id != expected_context_id
        or catalog.delivery_id != expected_delivery_id
        or (expected_catalog_id is not None and catalog.catalog_id != expected_catalog_id)
    ):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.STALE_CATALOG)
    try:
        index = next(index for index, spec in enumerate(catalog.specs) if spec.name == call.name)
    except StopIteration as exc:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.UNKNOWN_OPERATION) from exc
    spec = catalog.specs[index]
    binding = catalog.bindings[index]
    try:
        validate_value(call.arguments, spec.input_schema, path="command")
    except ValueError as exc:
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.INVALID_ARGUMENTS,
            str(exc),
        ) from exc
    resolver = getattr(binding, "resolve", None)
    if not callable(resolver):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    try:
        decision = resolver(call.arguments, expected_context_id, call.call_id)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, GroundedToolResolutionError):
            raise
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.INVALID_ARGUMENTS,
            str(exc),
        ) from exc
    return decision if isinstance(decision, GroundedActionResolution) else GroundedActionResolution(decision)


def resolve_grounded_action_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_delivery_id: str,
    expected_catalog_id: str | None = None,
) -> GroundedActionResolution:
    outcome = resolve_grounded_tool_call(
        catalog,
        call,
        expected_context_id=expected_context_id,
        expected_delivery_id=expected_delivery_id,
        expected_catalog_id=expected_catalog_id,
    )
    if not isinstance(outcome, GroundedActionResolution):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return outcome


def _object_schema(properties: Mapping[str, object], required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _evidence_request_schema(
    purposes: tuple[str, ...],
    subjects: Mapping[str, str],
) -> Mapping[str, object]:
    visual_property = ObservationPurpose.VISUAL_PROPERTY.value
    subject_schema = {
        "type": "string",
        "description": "current_world or current E/N ref",
        "enum": sorted(subjects),
    }
    property_schema = {
        "type": "string",
        "description": "visual property to inspect",
        "enum": ["color", "icon", "visual_state", "appearance"],
    }
    variants: list[Mapping[str, object]] = []
    non_property_purposes = tuple(item for item in purposes if item != visual_property)
    if non_property_purposes:
        variants.append(
            _object_schema(
                {
                    "purpose": {
                        "type": "string",
                        "description": "kind of missing evidence",
                        "enum": list(non_property_purposes),
                    },
                    "subject": subject_schema,
                },
                ("purpose", "subject"),
            )
        )
    if visual_property in purposes:
        variants.append(
            _object_schema(
                {
                    "purpose": {
                        "type": "string",
                        "description": "kind of missing evidence",
                        "enum": [visual_property],
                    },
                    "subject": subject_schema,
                    "property": property_schema,
                },
                ("purpose", "subject", "property"),
            )
        )
    if len(variants) == 1:
        return variants[0]
    return {"oneOf": variants}


def _observation_tool_needed(context: AgentContext, capability) -> bool:
    current = tuple(
        source
        for source in context.actor_world.sources
        if source.modality == capability["modality"] and source.freshness == "current"
    )
    return not current or any(
        source.projection_coverage != "complete" or bool(context.actor_world.conflicts) for source in current
    )


_AGENT_PURPOSES = frozenset(
    {
        ObservationPurpose.ENTITY_DISCOVERY.value,
        ObservationPurpose.TARGET_DISAMBIGUATION.value,
        ObservationPurpose.VISUAL_PROPERTY.value,
        ObservationPurpose.SPATIAL_RELATIONSHIP.value,
        ObservationPurpose.TEXT_IN_IMAGE.value,
        ObservationPurpose.CRITERION_VERIFICATION.value,
    }
)


def _countable_child_groups(snapshot: ActorWorldSnapshot) -> Mapping[str, int]:
    """Return exact counts only for complete homogeneous public groups."""

    counts: dict[str, int] = {}

    def visit(node: ActorWorldNodeView) -> None:
        if len(node.children) >= 2 and _homogeneous_children(node.children):
            counts[node.ref] = len(node.children)
        for child in node.children:
            visit(child)

    for document in snapshot.documents:
        if not document.truncated:
            for root in document.roots:
                visit(root)
    return counts


def _homogeneous_children(children: tuple[ActorWorldNodeView, ...]) -> bool:
    first = children[0]
    shape = (first.role, first.label, first.state, len(first.children))
    return all((child.role, child.label, child.state, len(child.children)) == shape for child in children[1:])
