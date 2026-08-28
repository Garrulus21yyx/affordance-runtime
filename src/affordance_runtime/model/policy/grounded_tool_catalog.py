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
    BooleanFieldDraft,
    DateFieldDraft,
    DecimalFieldDraft,
    FinalResponse,
    IntegerFieldDraft,
    InteractionAttribute,
    InteractionOptionDraft,
    InteractionRequestDraft,
    InteractionResponseKind,
    PublicArtifactDraft,
    PublicArtifactItemDraft,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    TextFieldDraft,
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
from affordance_runtime.model.policy.perception import InteractionToolExposureProfile, ObservationToolExposureProfile
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
            public_intent=str(arguments.get("public_intent", "")).strip(),
        )


@dataclass(frozen=True)
class _EvidenceBinding:
    purposes: tuple[str, ...]
    subjects: Mapping[str, str]
    profile: ObservationToolExposureProfile

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        purpose = ObservationPurpose(str(arguments["purpose"]))
        try:
            if purpose.value not in self.purposes:
                raise ValueError("observation purpose was not offered by this Catalog")
            query_id = _observation_query_id(context_id, tool_call_id, arguments)
            if self.profile is ObservationToolExposureProfile.COMPATIBILITY:
                return self._resolve_compatibility(
                    arguments,
                    context_id=context_id,
                    query_id=query_id,
                    purpose=purpose,
                    tool_call_id=tool_call_id,
                )
            subject_ids = self._resolve_refs(arguments.get("subject_refs", ()))
            candidate_ids = self._resolve_refs(arguments.get("candidate_refs", ()))
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                subject_ids=subject_ids,
                candidate_ids=candidate_ids,
                atomic_query=str(arguments.get("atomic_query", "")).strip(),
                predicate=str(arguments.get("predicate", "")).strip(),
                max_results=int(arguments.get("max_results", 1)),
                public_intent=str(arguments.get("public_intent", "")).strip(),
                tool_call_id=tool_call_id,
            )
        except (KeyError, ValueError) as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS,
                str(exc),
            ) from exc

    def _resolve_refs(self, raw_refs: object) -> tuple[str, ...]:
        if not isinstance(raw_refs, list | tuple):
            raise ValueError("observation refs must be an array")
        refs = tuple(str(item) for item in raw_refs)
        if len(set(refs)) != len(refs) or any(item not in self.subjects for item in refs):
            raise ValueError("observation refs must be unique current DeliveryManifest refs")
        return tuple(self.subjects[item] for item in refs)

    def _resolve_compatibility(
        self,
        arguments: Mapping[str, object],
        *,
        context_id: str,
        query_id: str,
        purpose: ObservationPurpose,
        tool_call_id: str,
    ) -> RequestObservation:
        subject_ref = str(arguments["subject"])
        subject_id = self.subjects[subject_ref]
        if purpose is ObservationPurpose.ENTITY_DISCOVERY:
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                atomic_query="discover relevant visible entities",
                max_results=1,
                tool_call_id=tool_call_id,
            )
        if purpose is ObservationPurpose.VISUAL_PROPERTY:
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                subject_ids=(subject_id,),
                predicate=str(arguments["property"]),
                tool_call_id=tool_call_id,
            )
        if purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
            candidates = tuple(value for ref, value in self.subjects.items() if ref != "current_world")
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                candidate_ids=candidates,
                atomic_query="disambiguate the current visible candidates",
                tool_call_id=tool_call_id,
            )
        if purpose is ObservationPurpose.TEXT_IN_IMAGE:
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                subject_ids=(subject_id,),
                atomic_query="read relevant visible text",
                tool_call_id=tool_call_id,
            )
        if purpose is ObservationPurpose.SPATIAL_RELATIONSHIP:
            subjects = tuple(value for ref, value in self.subjects.items() if ref != "current_world")
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                subject_ids=subjects,
                predicate="determine the relevant spatial relationship",
                tool_call_id=tool_call_id,
            )
        if purpose is ObservationPurpose.CRITERION_VERIFICATION:
            return RequestObservation(
                context_id=context_id,
                query_id=query_id,
                purpose=purpose,
                subject_ids=(subject_id,),
                tool_call_id=tool_call_id,
            )
        raise ValueError("purpose is unavailable in compatibility observation schema")


@dataclass(frozen=True)
class _ControlBinding:
    kind: GroundedLocalToolName
    interaction_profile: InteractionToolExposureProfile = InteractionToolExposureProfile.COMPATIBILITY
    evidence_bindings: Mapping[str, str] | None = None
    media_refs: frozenset[str] = frozenset()

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        if self.kind is GroundedLocalToolName.ASK_USER:
            if self.interaction_profile is InteractionToolExposureProfile.STRUCTURED:
                return _resolve_interaction_draft(
                    arguments,
                    context_id=context_id,
                    tool_call_id=tool_call_id,
                    evidence_bindings=self.evidence_bindings or {},
                    media_refs=self.media_refs,
                )
            requested_fields = arguments.get("requested_fields", ())
            if not isinstance(requested_fields, list | tuple):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            fields = tuple(TextFieldDraft(str(item)) for item in requested_fields)
            return InteractionRequestDraft(
                context_id,
                str(arguments["question"]),
                (
                    InteractionResponseKind.STRUCTURED_FIELDS
                    if fields
                    else InteractionResponseKind.FREE_TEXT
                ),
                fields,
                tool_call_id=tool_call_id,
            )
        if self.kind is GroundedLocalToolName.WAIT:
            return Wait(
                context_id,
                str(arguments["reason"]),
                5_000,
                tool_call_id,
                str(arguments.get("public_intent", "")).strip(),
            )
        if self.kind is GroundedLocalToolName.ABORT:
            return Abort(
                context_id,
                str(arguments["reason"]),
                str(arguments["category"]),
                tool_call_id,
                str(arguments.get("public_intent", "")).strip(),
            )
        if self.kind is GroundedLocalToolName.SUBMIT_FINAL_RESPONSE:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)


@dataclass(frozen=True)
class _FinalResponseBinding:
    interaction_profile: InteractionToolExposureProfile = InteractionToolExposureProfile.COMPATIBILITY
    evidence_bindings: Mapping[str, str] | None = None

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        del tool_call_id
        artifact = None
        if self.interaction_profile is InteractionToolExposureProfile.STRUCTURED and "artifact" in arguments:
            artifact = _resolve_artifact_draft(arguments["artifact"], self.evidence_bindings or {})
        return FinalResponse(
            context_id,
            str(arguments["content"]),
            (),
            artifact,
            str(arguments.get("public_intent", "")).strip(),
        )


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
    observation_tool_profile: ObservationToolExposureProfile = ObservationToolExposureProfile.COMPATIBILITY,
    interaction_tool_profile: InteractionToolExposureProfile = InteractionToolExposureProfile.COMPATIBILITY,
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
    observation_tool_profile = ObservationToolExposureProfile(observation_tool_profile)
    interaction_tool_profile = InteractionToolExposureProfile(interaction_tool_profile)
    registered: list[RegisteredGroundedTool] = []

    purposes: set[str] = set()
    for capability in context.actor_world.observation_capabilities:
        if _observation_tool_needed(context, capability):
            purposes.update(
                set(capability["purposes"])
                & _purposes_for_exposure_profile(observation_tool_profile)
            )
    if purposes:
        refs = {
            ref: subject
            for ref, subject in context.grounding.private_subject_bindings().items()
            if ref in delivery.manifest.exact_refs
        }
        subjects = {"current_world": "current_world", **refs}
        ordered_purposes = tuple(sorted(purposes))
        if observation_tool_profile is ObservationToolExposureProfile.DYNAMIC_VISUAL:
            ordered_purposes = tuple(
                item
                for item in ordered_purposes
                if _dynamic_purpose_applicable(item, context, delivery, refs)
            )
        if ordered_purposes:
            schema = (
                _compatibility_evidence_request_schema(ordered_purposes, subjects)
                if observation_tool_profile is ObservationToolExposureProfile.COMPATIBILITY
                else _dynamic_evidence_request_schema(ordered_purposes, refs)
            )
            registered.append(
                RegisteredGroundedTool(
                    ToolSpec(
                        GroundedLocalToolName.REQUEST_EVIDENCE.value,
                        "Request missing current-world evidence; Runtime chooses how to obtain it.",
                        schema,
                    ),
                    _EvidenceBinding(ordered_purposes, subjects, observation_tool_profile),
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
            include_public_intent=(
                interaction_tool_profile is InteractionToolExposureProfile.STRUCTURED
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
                                "description": "optional non-empty next_cursor returned by this same tool",
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
                                "description": "optional non-empty next_cursor returned by this same tool",
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
                                "description": "optional non-empty next_cursor returned by this same tool",
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
    evidence_bindings = {
        ref: canonical
        for ref, canonical in context.private_fact_bindings.items()
        if ref in delivery.manifest.fact_refs
    }
    evidence_bindings.update({item.evidence_ref: item.evidence_ref for item in delivery.media})
    media_refs = frozenset(item.evidence_ref for item in delivery.media)
    final_properties: dict[str, object] = {
        "content": {
            "type": "string",
            "description": "complete final answer, JSON when the task contract requires JSON",
            "minLength": 1,
            "maxLength": 8000,
        },
    }
    if interaction_tool_profile is InteractionToolExposureProfile.STRUCTURED:
        final_properties.update(
            {
                "artifact": _artifact_draft_schema(tuple(sorted(evidence_bindings))),
                "public_intent": _public_intent_schema(),
            }
        )
    registered.append(
        RegisteredGroundedTool(
            ToolSpec(
                GroundedLocalToolName.SUBMIT_FINAL_RESPONSE.value,
                _final_response_description(context.final_response_guidance),
                _object_schema(final_properties, ("content",)),
            ),
            _FinalResponseBinding(interaction_tool_profile, evidence_bindings),
        )
    )

    ask_schema = (
        _structured_interaction_request_schema(
            tuple(sorted(evidence_bindings)),
            tuple(sorted(media_refs)),
        )
        if interaction_tool_profile is InteractionToolExposureProfile.STRUCTURED
        else _object_schema(
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
        )
    )
    sidecar = (
        {"public_intent": _public_intent_schema()}
        if interaction_tool_profile is InteractionToolExposureProfile.STRUCTURED
        else {}
    )
    registered.extend(
        (
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.ASK_USER.value,
                    "Ask for task information unavailable in the interface.",
                    ask_schema,
                ),
                _ControlBinding(
                    GroundedLocalToolName.ASK_USER,
                    interaction_tool_profile,
                    evidence_bindings,
                    media_refs,
                ),
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
                            **sidecar,
                        },
                        ("reason",),
                    ),
                ),
                _ControlBinding(GroundedLocalToolName.WAIT, interaction_tool_profile),
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
                            **sidecar,
                        },
                        ("reason", "category"),
                    ),
                ),
                _ControlBinding(GroundedLocalToolName.ABORT, interaction_tool_profile),
            ),
        )
    )
    return _catalog_from_registrations(
        context,
        delivery,
        tuple(registered),
        observation_tool_profile=observation_tool_profile,
        interaction_tool_profile=interaction_tool_profile,
    )


def _catalog_from_registrations(
    context: AgentContext,
    delivery: ModelTurnDelivery,
    registered: tuple[RegisteredGroundedTool, ...],
    *,
    observation_tool_profile: ObservationToolExposureProfile,
    interaction_tool_profile: InteractionToolExposureProfile,
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
    digest = hashlib.sha256(
        f"{context.context_id}\0{delivery.delivery_id}\0{observation_tool_profile.digest}\0{interaction_tool_profile.digest}\0{encoded}".encode()
    ).hexdigest()[:32]
    catalog_id = f"grounded-catalog:{digest}"
    return GroundedToolCatalog(
        catalog_id,
        context.context_id,
        delivery.delivery_id,
        delivery.manifest,
        context.region_index,
        registered,
        encoded_bytes,
        observation_tool_profile.value,
        observation_tool_profile.digest,
        interaction_tool_profile.value,
        interaction_tool_profile.digest,
    )


def compile_grounded_action_catalog(
    context: AgentContext,
    delivery: ModelTurnDelivery,
    observation_tool_profile: ObservationToolExposureProfile = ObservationToolExposureProfile.COMPATIBILITY,
    interaction_tool_profile: InteractionToolExposureProfile = InteractionToolExposureProfile.COMPATIBILITY,
) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
        observation_tool_profile,
        interaction_tool_profile,
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


def _public_intent_schema() -> Mapping[str, object]:
    return {
        "type": "string",
        "description": "optional short user-visible intent; never a completion claim",
        "minLength": 1,
        "maxLength": 240,
    }


def _attributes_schema() -> Mapping[str, object]:
    return {
        "type": "array",
        "maxItems": 16,
        "items": _object_schema(
            {
                "label": {"type": "string", "minLength": 1, "maxLength": 120},
                "value": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            ("label", "value"),
        ),
    }


def _evidence_refs_schema(evidence_refs: tuple[str, ...]) -> Mapping[str, object]:
    if not evidence_refs:
        raise ValueError("evidence ref schema requires a non-empty current domain")
    return {
        "type": "array",
        "items": {"type": "string", "enum": list(evidence_refs)},
        "maxItems": min(32, len(evidence_refs)),
    }


def _option_draft_schema(
    evidence_refs: tuple[str, ...],
    media_refs: tuple[str, ...],
) -> Mapping[str, object]:
    properties: dict[str, object] = {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "description": {"type": "string", "maxLength": 1000},
        "attributes": _attributes_schema(),
        "uncertainties": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 32,
        },
    }
    if evidence_refs:
        properties["evidence_refs"] = _evidence_refs_schema(evidence_refs)
    if media_refs:
        properties["media_ref"] = {"type": "string", "enum": list(media_refs)}
    return _object_schema(properties, ("title",))


def _field_draft_schema() -> Mapping[str, object]:
    variants = []
    for kind in ("text", "integer", "decimal", "boolean", "date"):
        variants.append(
            _object_schema(
                {
                    "kind": {"type": "string", "enum": [kind]},
                    "label": {"type": "string", "minLength": 1, "maxLength": 120},
                    "description": {"type": "string", "maxLength": 500},
                    "required": {"type": "boolean"},
                },
                ("kind", "label"),
            )
        )
    return {"oneOf": variants}


def _structured_interaction_request_schema(
    evidence_refs: tuple[str, ...],
    media_refs: tuple[str, ...],
) -> Mapping[str, object]:
    prompt = {"type": "string", "minLength": 1, "maxLength": 1000}
    intent = _public_intent_schema()
    common = {"prompt": prompt, "public_intent": intent}
    return {
        "type": "object",
        "oneOf": [
            _object_schema(
                {**common, "response_kind": {"type": "string", "enum": ["free_text"]}},
                ("prompt", "response_kind"),
            ),
            *(
                _object_schema(
                    {
                        **common,
                        "response_kind": {"type": "string", "enum": [kind]},
                        "option_drafts": {
                            "type": "array",
                            "items": _option_draft_schema(evidence_refs, media_refs),
                            "minItems": 1,
                            "maxItems": 32,
                        },
                    },
                    ("prompt", "response_kind", "option_drafts"),
                )
                for kind in ("single_select", "multi_select")
            ),
            _object_schema(
                {
                    **common,
                    "response_kind": {"type": "string", "enum": ["structured_fields"]},
                    "field_drafts": {
                        "type": "array",
                        "items": _field_draft_schema(),
                        "minItems": 1,
                        "maxItems": 32,
                    },
                },
                ("prompt", "response_kind", "field_drafts"),
            ),
        ]
    }


def _artifact_draft_schema(evidence_refs: tuple[str, ...]) -> Mapping[str, object]:
    item_properties: dict[str, object] = {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "summary": {"type": "string", "maxLength": 1000},
        "attributes": _attributes_schema(),
    }
    if evidence_refs:
        item_properties["evidence_refs"] = _evidence_refs_schema(evidence_refs)
    item = _object_schema(
        item_properties,
        ("title",),
    )
    artifact_properties: dict[str, object] = {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "summary": {"type": "string", "maxLength": 2000},
        "items": {"type": "array", "items": item, "maxItems": 32},
    }
    if evidence_refs:
        artifact_properties["evidence_refs"] = _evidence_refs_schema(evidence_refs)
    return _object_schema(
        artifact_properties,
        ("title",),
    )


def _resolve_interaction_draft(
    arguments: Mapping[str, object],
    *,
    context_id: str,
    tool_call_id: str,
    evidence_bindings: Mapping[str, str],
    media_refs: frozenset[str],
) -> InteractionRequestDraft:
    raw_fields = arguments.get("field_drafts", ())
    raw_options = arguments.get("option_drafts", ())
    if not isinstance(raw_fields, list | tuple) or not isinstance(raw_options, list | tuple):
        raise ValueError("interaction draft collections must be arrays")
    fields = tuple(_resolve_field_draft(item) for item in raw_fields)
    options = tuple(
        _resolve_option_draft(item, evidence_bindings, media_refs)
        for item in raw_options
    )
    return InteractionRequestDraft(
        context_id,
        str(arguments["prompt"]),
        InteractionResponseKind(str(arguments["response_kind"])),
        fields,
        options,
        str(arguments.get("public_intent", "")).strip(),
        tool_call_id,
    )


def _resolve_field_draft(value: object):
    if not isinstance(value, Mapping):
        raise ValueError("interaction field draft must be an object")
    common = (
        str(value["label"]),
        str(value.get("description", "")),
        bool(value.get("required", True)),
    )
    field_type = {
        "text": TextFieldDraft,
        "integer": IntegerFieldDraft,
        "decimal": DecimalFieldDraft,
        "boolean": BooleanFieldDraft,
        "date": DateFieldDraft,
    }.get(str(value["kind"]))
    if field_type is None:
        raise ValueError("interaction field kind is unsupported")
    return field_type(*common)


def _resolve_option_draft(
    value: object,
    evidence_bindings: Mapping[str, str],
    media_refs: frozenset[str],
) -> InteractionOptionDraft:
    if not isinstance(value, Mapping):
        raise ValueError("interaction option draft must be an object")
    media_ref = str(value.get("media_ref", ""))
    if media_ref and media_ref not in media_refs:
        raise ValueError("interaction option media is outside the current delivery")
    return InteractionOptionDraft(
        str(value["title"]),
        str(value.get("description", "")),
        media_ref,
        _resolve_attributes(value.get("attributes", ())),
        _resolve_evidence_refs(value.get("evidence_refs", ()), evidence_bindings),
        tuple(str(item) for item in _array(value.get("uncertainties", ()))),
    )


def _resolve_artifact_draft(
    value: object,
    evidence_bindings: Mapping[str, str],
) -> PublicArtifactDraft:
    if not isinstance(value, Mapping):
        raise ValueError("artifact draft must be an object")
    return PublicArtifactDraft(
        str(value["title"]),
        str(value.get("summary", "")),
        tuple(
            PublicArtifactItemDraft(
                str(item["title"]),
                str(item.get("summary", "")),
                _resolve_attributes(item.get("attributes", ())),
                _resolve_evidence_refs(item.get("evidence_refs", ()), evidence_bindings),
            )
            for raw in _array(value.get("items", ()))
            for item in (raw if isinstance(raw, Mapping) else {},)
        ),
        _resolve_evidence_refs(value.get("evidence_refs", ()), evidence_bindings),
    )


def _resolve_attributes(value: object) -> tuple[InteractionAttribute, ...]:
    return tuple(
        InteractionAttribute(str(item["label"]), str(item["value"]))
        for raw in _array(value)
        for item in (raw if isinstance(raw, Mapping) else {},)
    )


def _resolve_evidence_refs(
    value: object,
    evidence_bindings: Mapping[str, str],
) -> tuple[str, ...]:
    refs = tuple(str(item) for item in _array(value))
    if any(item not in evidence_bindings for item in refs):
        raise ValueError("presentation evidence is outside the current delivery")
    return tuple(evidence_bindings[item] for item in refs)


def _array(value: object) -> tuple[object, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("structured tool field must be an array")
    return tuple(value)


def _compatibility_evidence_request_schema(
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
    return {"type": "object", "oneOf": variants}


def _dynamic_evidence_request_schema(
    purposes: tuple[str, ...],
    subjects: Mapping[str, str],
) -> Mapping[str, object]:
    refs = sorted(subjects)
    ref_items = {
        "type": "string",
        "description": "current readable E/N ref from this delivery",
        "enum": refs,
    }
    public_intent = {
        "type": "string",
        "description": "optional short user-visible intent",
        "minLength": 1,
        "maxLength": 240,
    }
    atomic_query = {
        "type": "string",
        "description": "one bounded visual question, never the overall task goal",
        "minLength": 1,
        "maxLength": 500,
    }
    predicate = {
        "type": "string",
        "description": "one bounded observable predicate",
        "minLength": 1,
        "maxLength": 500,
    }

    def ref_array(minimum: int) -> Mapping[str, object]:
        return {
            "type": "array",
            "description": "ordered unique current refs",
            "items": ref_items,
            "minItems": minimum,
            "maxItems": min(32, len(refs)),
        }

    variants: list[Mapping[str, object]] = []
    for purpose in purposes:
        purpose_schema = {"type": "string", "enum": [purpose]}
        properties: dict[str, object] = {
            "purpose": purpose_schema,
            "public_intent": public_intent,
        }
        required = ["purpose"]
        if purpose == ObservationPurpose.ENTITY_DISCOVERY.value:
            properties.update(
                {
                    "atomic_query": atomic_query,
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 32},
                }
            )
            required.extend(("atomic_query", "max_results"))
        elif purpose == ObservationPurpose.VISUAL_PROPERTY.value:
            properties.update({"subject_refs": ref_array(1), "predicate": predicate})
            required.extend(("subject_refs", "predicate"))
        elif purpose == ObservationPurpose.TARGET_DISAMBIGUATION.value:
            properties.update({"candidate_refs": ref_array(2), "atomic_query": atomic_query})
            required.extend(("candidate_refs", "atomic_query"))
        elif purpose == ObservationPurpose.POINT_GROUNDING.value:
            properties["atomic_query"] = atomic_query
            if refs:
                properties["candidate_refs"] = ref_array(1)
            required.append("atomic_query")
        elif purpose == ObservationPurpose.TEXT_IN_IMAGE.value:
            properties.update({"subject_refs": ref_array(1), "atomic_query": atomic_query})
            required.extend(("subject_refs", "atomic_query"))
        elif purpose == ObservationPurpose.SPATIAL_RELATIONSHIP.value:
            properties.update({"subject_refs": ref_array(2), "predicate": predicate})
            required.extend(("subject_refs", "predicate"))
        elif purpose == ObservationPurpose.VISUAL_CHANGE.value:
            properties.update({"subject_refs": ref_array(1), "predicate": predicate})
            required.extend(("subject_refs", "predicate"))
        else:  # pragma: no cover - guarded by the typed exposure set
            raise ValueError(f"unsupported dynamic observation purpose: {purpose}")
        variants.append(_object_schema(properties, tuple(required)))
    if len(variants) == 1:
        return variants[0]
    return {"type": "object", "oneOf": variants}


def _observation_query_id(
    context_id: str,
    tool_call_id: str,
    arguments: Mapping[str, object],
) -> str:
    encoded = json.dumps(to_json_compatible(arguments), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(f"{context_id}\0{tool_call_id}\0{encoded}".encode()).hexdigest()[:24]
    return f"observation-query:{digest}"


def _purposes_for_exposure_profile(profile: ObservationToolExposureProfile) -> frozenset[str]:
    if profile is ObservationToolExposureProfile.COMPATIBILITY:
        return _COMPATIBILITY_AGENT_PURPOSES
    return _DYNAMIC_VISUAL_PURPOSES


def _dynamic_purpose_applicable(
    purpose: str,
    context: AgentContext,
    delivery: ModelTurnDelivery,
    refs: Mapping[str, str],
) -> bool:
    del delivery  # refs were already intersected with this exact manifest
    ref_count = len(refs)
    if purpose == ObservationPurpose.ENTITY_DISCOVERY.value:
        return bool(context.actor_world.media) and (
            any(document.truncated for document in context.actor_world.documents)
            or any(source.projection_coverage != "complete" for source in context.actor_world.sources)
        )
    if purpose in {
        ObservationPurpose.VISUAL_PROPERTY.value,
        ObservationPurpose.TEXT_IN_IMAGE.value,
    }:
        return ref_count >= 1
    if purpose in {
        ObservationPurpose.TARGET_DISAMBIGUATION.value,
        ObservationPurpose.SPATIAL_RELATIONSHIP.value,
    }:
        return ref_count >= 2
    if purpose == ObservationPurpose.POINT_GROUNDING.value:
        return bool(context.actor_world.media)
    if purpose == ObservationPurpose.VISUAL_CHANGE.value:
        return ref_count >= 1
    return False


def _observation_tool_needed(context: AgentContext, capability) -> bool:
    current = tuple(
        source
        for source in context.actor_world.sources
        if source.modality == capability["modality"] and source.freshness == "current"
    )
    return not current or any(
        source.projection_coverage != "complete" or bool(context.actor_world.conflicts) for source in current
    )


_COMPATIBILITY_AGENT_PURPOSES = frozenset(
    {
        ObservationPurpose.ENTITY_DISCOVERY.value,
        ObservationPurpose.TARGET_DISAMBIGUATION.value,
        ObservationPurpose.VISUAL_PROPERTY.value,
        ObservationPurpose.SPATIAL_RELATIONSHIP.value,
        ObservationPurpose.TEXT_IN_IMAGE.value,
        ObservationPurpose.CRITERION_VERIFICATION.value,
    }
)

_DYNAMIC_VISUAL_PURPOSES = frozenset(
    {
        ObservationPurpose.ENTITY_DISCOVERY.value,
        ObservationPurpose.TARGET_DISAMBIGUATION.value,
        ObservationPurpose.VISUAL_PROPERTY.value,
        ObservationPurpose.SPATIAL_RELATIONSHIP.value,
        ObservationPurpose.TEXT_IN_IMAGE.value,
        ObservationPurpose.POINT_GROUNDING.value,
        ObservationPurpose.VISUAL_CHANGE.value,
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
