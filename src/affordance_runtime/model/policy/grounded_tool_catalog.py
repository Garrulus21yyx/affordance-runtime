"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Mapping

from affordance_runtime.actions.paging import PUBLIC_ACTION_LABEL_MAX_CHARS
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView, ActorWorldSnapshot
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveryManifest,
    Matches,
    Opened,
    Page,
    inspect_actor_world,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.model_turn_delivery import ModelTurnDelivery
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    ContinueDeliveryResult,
    FinalResponse,
    ReadRegionResult,
    RememberFactResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    Wait,
)
from affordance_runtime.agent.working_facts import (
    WorkingFact,
    is_public_scalar,
    validate_working_fact_collection,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
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
    REMEMBER_FACT = "remember_fact"
    READ_REGION = "read_region"
    SEARCH_PAGE_CONTENT = "search_page_content"
    LIST_REGIONS = "list_regions"
    FIND_CONTROLS = "find_controls"
    READ_NEXT_PAGE = "read_next_page"
    ACTION_RESULTS_NEXT_PAGE = "action_results_next_page"
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
class _ActionResultsNextPageBinding:
    context: AgentContext
    delivery: ModelTurnDelivery
    scopes: tuple[str, ...]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> GroundedActionResolution:
        scope = str(arguments.get("scope", "")) if arguments else ""
        if not scope and len(self.scopes) == 1:
            scope = self.scopes[0]
        if scope not in self.scopes or set(arguments).difference({"scope"}):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        plan = self.context.action_delivery_plan
        obligation = next(
            (item for item in plan.obligations if item.continuation_scope == scope),
            None,
        ) if plan is not None else None
        admitted = dict(self.delivery.admitted_record_counts).get(obligation.kind.value, 0) if obligation else 0
        if obligation is None or admitted <= 0 or admitted >= len(obligation.remaining):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        new_offset = obligation.cursor.offset + admitted
        advance_cursor = getattr(self.context.delivery_store, "with_advanced_cursor", None)
        if not callable(advance_cursor):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        next_store = advance_cursor(
            scope,
            world_lineage=obligation.cursor.world_lineage,
            action_lineage=obligation.cursor.action_space_lineage,
            result_lineage=obligation.cursor.effect_or_result_lineage,
            order_digest=obligation.cursor.order_digest,
            offset=new_offset,
        )
        return GroundedActionResolution(
            ContinueDeliveryResult(
                context_id,
                GroundedLocalToolName.ACTION_RESULTS_NEXT_PAGE.value,
                {"scope": scope},
                {
                    "continuation_available": new_offset < len(obligation.records),
                    "continuation_scope": scope,
                    "read_only": True,
                    "zero_browser_dispatch": True,
                },
                tool_call_id,
            ),
            next_store,
        )


@dataclass(frozen=True)
class _ManifestBoundAction:
    inner: object
    manifest: DeliveryManifest

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision | GroundedActionResolution:
        for name in ("target", "source", "destination"):
            value = arguments.get(name)
            if isinstance(value, str) and not self.manifest.admits_executable(value):
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.GROUNDING_GAP,
                    f"{name} is not exact in the current DeliveryManifest",
                )
        resolver = getattr(self.inner, "resolve", None)
        if not callable(resolver):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        return resolver(arguments, context_id, tool_call_id)


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
    public_to_canonical: Mapping[str, str]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        del tool_call_id
        raw_refs = arguments.get("evidence_refs", ())
        if not isinstance(raw_refs, list | tuple):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        try:
            canonical_refs = tuple(self.public_to_canonical[str(ref)] for ref in raw_refs)
        except KeyError as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.GROUNDING_GAP,
                "final response evidence_ref is not a current public fact",
            ) from exc
        return FinalResponse(context_id, str(arguments["content"]), canonical_refs)


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
class _RememberFactBinding:
    public_to_canonical: Mapping[str, str]
    evidence_index: WorldEvidenceIndex
    existing: Mapping[str, WorkingFact]
    current_step_index: int

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        key = str(arguments["key"])
        public_ref = str(arguments["evidence_ref"])
        purpose = str(arguments["purpose"])
        try:
            canonical = self.public_to_canonical[public_ref]
        except KeyError as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.GROUNDING_GAP,
                "evidence_ref is not a current public scalar fact",
            ) from exc
        record = self.evidence_index.resolve_record(canonical)
        if record is None:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS,
                "evidence_ref is stale",
            )
        fact = WorkingFact(key, record, self.current_step_index, purpose)
        previous = self.existing.get(key)
        if previous is not None:
            if previous.record.evidence_ref != fact.record.evidence_ref:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.INVALID_ARGUMENTS,
                    "working fact key already identifies different evidence",
                )
            return RememberFactResult(
                context_id,
                GroundedLocalToolName.REMEMBER_FACT.value,
                {"key": key, "evidence_ref": public_ref, "purpose": purpose},
                {"status": "already_remembered", "key": key},
                tool_call_id,
            )
        try:
            validate_working_fact_collection((*self.existing.values(), fact))
        except ValueError as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS,
                str(exc),
            ) from exc
        return RememberFactResult(
            context_id,
            GroundedLocalToolName.REMEMBER_FACT.value,
            {"key": key, "evidence_ref": public_ref, "purpose": purpose},
            {"status": "remembered", "key": key},
            tool_call_id,
            working_fact=fact,
        )


@dataclass(frozen=True)
class _WorldReadBinding:
    context: AgentContext
    kind: str
    continuation_scopes: tuple[str, ...] = ()
    delivery: ModelTurnDelivery | None = None

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision | GroundedActionResolution:
        observation, region_index = _current_world_read_authority(self.context)
        region_ref = ""
        query = ""
        page_cursor = ""
        if self.kind == "region":
            tool_name = GroundedLocalToolName.READ_REGION.value
            action = "read_region"
            region_ref = str(arguments["region_ref"])
        elif self.kind == "find":
            tool_name = GroundedLocalToolName.SEARCH_PAGE_CONTENT.value
            action = "find"
            query = str(arguments["query"]).strip()
        elif self.kind == "view_all":
            tool_name = GroundedLocalToolName.LIST_REGIONS.value
            action = "view_all"
        elif self.kind == "continue":
            scope = str(arguments.get("scope", "")) if arguments else ""
            if not scope and len(self.continuation_scopes) == 1:
                scope = self.continuation_scopes[0]
            if scope not in self.continuation_scopes or set(arguments).difference({"scope"}):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            if scope in {"effect", "page_directory"}:
                return self._continue_obligation(scope, context_id, tool_call_id)
            lens = getattr(self.context.delivery_store, "active_read", None)
            if lens is None or not lens.next_cursor:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.INVALID_ARGUMENTS,
                    "no current World read has another page",
                )
            tool_name = GroundedLocalToolName.READ_NEXT_PAGE.value
            page_cursor = lens.next_cursor
            if lens.kind == "region":
                action = "read_region"
                region = region_index.get(lens.selected_region_key)
                if region is None:
                    raise GroundedToolResolutionError(GroundedToolResolutionCode.STALE_CATALOG)
                region_ref = self.context.canonical_world.region_refs[region.key]
            elif lens.kind == "find":
                action = "find"
                query = lens.query
            elif lens.kind == "view_all":
                action = "view_all"
            else:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
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
        lens = _next_world_delivery_lens(
            observation.observation_id,
            region_index,
            self.context.canonical_world,
            action,
            region_ref,
            query,
            page_cursor,
            result,
        )
        store = self.context.delivery_store
        replace_active_read = getattr(store, "with_active_read", None)
        if not callable(replace_active_read):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        next_store = replace_active_read(lens)
        public_arguments: Mapping[str, object]
        if tool_name == GroundedLocalToolName.READ_REGION.value:
            public_arguments = {"region_ref": region_ref}
        elif tool_name == GroundedLocalToolName.SEARCH_PAGE_CONTENT.value:
            public_arguments = {"query": query}
        elif tool_name == GroundedLocalToolName.READ_NEXT_PAGE.value:
            public_arguments = {"scope": "active_read"}
        else:
            public_arguments = {}
        public_result = dict(inspect_outcome_public(result))
        public_result.update(
            {
                "searched_domain": "readable_content",
                "read_only": True,
                "zero_browser_dispatch": True,
                "does_not_search": "executable_controls",
            }
        )
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
            next_store,
        )

    def _continue_obligation(
        self, scope: str, context_id: str, tool_call_id: str
    ) -> GroundedActionResolution:
        plan = self.context.action_delivery_plan
        delivery = self.delivery
        if plan is None or delivery is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        obligation = next(
            (item for item in plan.obligations if item.continuation_scope == scope),
            None,
        )
        admitted = dict(delivery.admitted_record_counts).get(obligation.kind.value, 0) if obligation else 0
        if obligation is None or admitted <= 0 or admitted >= len(obligation.remaining):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        new_offset = obligation.cursor.offset + admitted
        store = self.context.delivery_store
        advance_cursor = getattr(store, "with_advanced_cursor", None)
        if not callable(advance_cursor):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        next_store = advance_cursor(
            scope,
            world_lineage=obligation.cursor.world_lineage,
            action_lineage=obligation.cursor.action_space_lineage,
            result_lineage=obligation.cursor.effect_or_result_lineage,
            order_digest=obligation.cursor.order_digest,
            offset=new_offset,
        )
        return GroundedActionResolution(
            ReadRegionResult(
                context_id,
                GroundedLocalToolName.READ_NEXT_PAGE.value,
                {"scope": scope},
                {
                    "read_only": True,
                    "zero_browser_dispatch": True,
                    "continuation_available": new_offset < len(obligation.records),
                    "continuation_scope": scope,
                },
                tool_call_id,
            ),
            next_store,
        )


def _current_world_read_authority(context: AgentContext):
    if context.current_observation is None or context.region_index is None:
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.CATALOG_INVALID,
            "World reading requires a current observation and region index",
        )
    return context.current_observation, context.region_index


def _next_world_delivery_lens(
    observation_id,
    region_index,
    canonical_world,
    action,
    region_ref,
    query,
    page_cursor,
    result,
):
    if isinstance(result, Opened):
        region = region_index.get(canonical_world.resolve_region_ref(region_ref))
        if region is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.STALE_CATALOG)
        return WorldDeliveryLens(
            observation_id,
            "region",
            region.key,
            "",
            page_cursor,
            result.next_cursor,
        )
    if isinstance(result, Matches) and result.items:
            return WorldDeliveryLens(
                observation_id,
                "find",
                "",
                query,
                page_cursor,
                result.next_cursor,
            )
    if isinstance(result, Page):
        return WorldDeliveryLens(
            observation_id,
            "view_all",
            "",
            "",
            page_cursor,
            result.next_cursor,
        )
    return None


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
            _ManifestBoundAction(item, delivery.manifest),
        )
        for item in GroundedToolCompiler().compile(
            _delivered_action_options(context, delivery.manifest),
            context_id=context.context_id,
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

    if context.evidence_index is not None:
        eligible = {
            public: canonical
            for public, canonical in context.private_fact_bindings.items()
            if (
                public in delivery.manifest.fact_refs
                and (record := context.evidence_index.resolve_record(canonical)) is not None
                and is_public_scalar(record.value)
            )
        }
        if eligible:
            registered.append(
                RegisteredGroundedTool(
                    ToolSpec(
                        GroundedLocalToolName.REMEMBER_FACT.value,
                        "Remember one current scalar F-ref for this episode.",
                        _object_schema(
                            {
                                "key": {
                                    "type": "string",
                                    "description": "name for the remembered fact",
                                    "pattern": "^[a-z][a-z0-9_]{0,63}$",
                                },
                                "evidence_ref": {
                                    "type": "string",
                                    "description": "current scalar F-ref",
                                    "enum": sorted(eligible),
                                },
                                "purpose": {
                                    "type": "string",
                                    "description": "why it is needed later",
                                    "minLength": 1,
                                    "maxLength": 240,
                                },
                            },
                            ("key", "evidence_ref", "purpose"),
                        ),
                    ),
                    _RememberFactBinding(
                        eligible,
                        context.evidence_index,
                        {item.key: item for item in context.workspace.working_facts},
                        context.current_step_index,
                    ),
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
                                "description": "current PageMap R-ref",
                                "enum": sorted(delivery.manifest.region_refs),
                            }
                        },
                        ("region_ref",),
                    ),
                ),
                _WorldReadBinding(context, "region"),
            )
        )
    registered.extend(
        (
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.SEARCH_PAGE_CONTENT.value,
                    "Find readable text, values, or facts in the complete current World; no browser action.",
                    _object_schema(
                        {
                            "query": {
                                "type": "string",
                                "description": "text to find in the current World",
                                "minLength": 1,
                                "maxLength": 120,
                            }
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
                    _object_schema({}),
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
    plan = context.action_delivery_plan
    read_scopes: list[str] = []
    active_read = getattr(context.delivery_store, "active_read", None)
    if active_read is not None and active_read.next_cursor:
        read_scopes.append("active_read")
    admitted_counts = dict(delivery.admitted_record_counts)
    if plan is not None:
        for scope in ("effect", "page_directory"):
            obligation = next((item for item in plan.obligations if item.continuation_scope == scope), None)
            if obligation is not None and 0 < admitted_counts.get(obligation.kind.value, 0) < len(obligation.remaining):
                read_scopes.append(scope)
    if read_scopes:
        properties = (
            {
                "scope": {
                    "type": "string",
                    "description": "which bounded current World delivery to continue",
                    "enum": read_scopes,
                }
            }
            if len(read_scopes) > 1
            else {}
        )
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.READ_NEXT_PAGE.value,
                    "Continue a current World delivery page; Runtime owns paging.",
                    _object_schema(properties, ("scope",) if properties else ()),
                ),
                _WorldReadBinding(context, "continue", tuple(read_scopes), delivery),
            )
        )
    continuation_scopes = tuple(
        item.continuation_scope
        for item in (plan.obligations if plan is not None else ())
        if item.continuation_scope not in {"effect", "page_directory"}
        and 0 < admitted_counts.get(item.kind.value, 0) < len(item.remaining)
    )
    if continuation_scopes:
        properties = (
            {
                "scope": {
                    "type": "string",
                    "description": "which independent action result cursor to continue",
                    "enum": continuation_scopes,
                }
            }
            if len(continuation_scopes) > 1
            else {}
        )
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.ACTION_RESULTS_NEXT_PAGE.value,
                    "Continue current action results; Runtime owns paging.",
                    _object_schema(properties, ("scope",) if properties else ()),
                ),
                _ActionResultsNextPageBinding(context, delivery, continuation_scopes),
            )
        )

    final_evidence = {
        public: canonical
        for public, canonical in context.private_fact_bindings.items()
        if public in delivery.manifest.fact_refs
    }
    registered.append(
        RegisteredGroundedTool(
            ToolSpec(
                GroundedLocalToolName.SUBMIT_FINAL_RESPONSE.value,
                "Submit the complete final answer from the current World directly for native evaluation.",
                _object_schema(
                    {
                        "content": {
                            "type": "string",
                            "description": "complete final answer, JSON when the task contract requires JSON",
                            "minLength": 1,
                            "maxLength": 8000,
                        },
                        "evidence_refs": {
                            "type": "array",
                            "description": "optional current F-refs for traceability",
                            "items": (
                                PublicRefCodec.enum_schema(
                                    tuple(sorted(final_evidence)),
                                    expected=PublicRefKind.FACT,
                                )
                                if final_evidence
                                else {"type": "string"}
                            ),
                            "maxItems": min(32, len(final_evidence)),
                        },
                    },
                    ("content",),
                ),
            ),
            _FinalResponseBinding(final_evidence),
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


def _delivered_action_options(
    context: AgentContext,
    manifest: DeliveryManifest,
):
    routes = {
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    }
    delivered = []
    for option in context.complete_actions:
        if option.destination_required:
            destinations = tuple(
                item
                for item in option.destinations.items
                if (option.operation, option.target_ref, item.grounding_ref) in routes
            )
            if destinations:
                delivered.append(
                    replace(
                        option,
                        destinations=BoundedSection(destinations, len(destinations), False),
                    )
                )
        elif (option.operation, option.target_ref, "") in routes:
            delivered.append(option)
    return tuple(delivered)


def compile_grounded_action_catalog(
    context: AgentContext,
    delivery: ModelTurnDelivery,
) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
    )


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
