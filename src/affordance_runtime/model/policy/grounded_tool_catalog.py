"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView, ActorWorldSnapshot
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
    FinalResponse,
    FormFieldUpdate,
    ReadRegionResult,
    RememberFactResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SetFormFields,
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
    MAX_GROUNDED_WORKSPACE_BYTES,
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    RegisteredGroundedTool,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.world.observation_needs import ObservationPurpose


class GroundedLocalToolName(StrEnum):
    """Closed non-ActionSpace vocabulary owned by the grounded ToolCatalog."""

    REQUEST_EVIDENCE = "request_evidence"
    COUNT_CHILDREN = "count_children"
    REMEMBER_FACT = "remember_fact"
    READ_REGION = "read_region"
    SEARCH_PAGE_CONTENT = "search_page_content"
    LIST_REGIONS = "list_regions"
    FIND_CONTROLS = "find_controls"
    SET_FORM_FIELDS = "set_form_fields"
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
class _FormFieldAction:
    action_id: str
    operation: str
    target_ref: str
    parameter_schema: Mapping[str, object]


@dataclass(frozen=True)
class _SetFormFieldsBinding:
    forms: Mapping[str, Mapping[tuple[str, str], _FormFieldAction]]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        form_key = str(arguments.get("form", ""))
        raw_fields = arguments.get("fields")
        form = self.forms.get(form_key)
        if form is None or not isinstance(raw_fields, list | tuple) or not 2 <= len(raw_fields) <= 4:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        updates: list[FormFieldUpdate] = []
        seen: set[str] = set()
        for raw in raw_fields:
            if not isinstance(raw, Mapping):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            target_ref = str(raw.get("target", ""))
            operation = str(raw.get("operation", ""))
            action = form.get((target_ref, operation))
            if action is None or target_ref in seen:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            seen.add(target_ref)
            parameters = {"text" if operation == "type_text" else "value": raw.get("value")}
            try:
                validate_value(parameters, action.parameter_schema, path="command")
            except ValueError as exc:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
            updates.append(
                FormFieldUpdate(
                    action.action_id,
                    operation,
                    target_ref,
                    parameters,
                )
            )
        return SetFormFields(context_id, form_key, tuple(updates), tool_call_id)


@dataclass(frozen=True)
class _ActionResultsNextPageBinding:
    active_query: str
    active_target_id: str
    active_relevance_role: str
    next_cursor: str

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        if arguments or not self.next_cursor:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        return RequestActionPage(
            context_id,
            self.active_query,
            self.active_target_id,
            self.active_relevance_role,
            self.next_cursor,
            tool_call_id,
        )


@dataclass(frozen=True)
class _ManifestBoundAction:
    inner: object
    manifest: DeliveryManifest

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
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
        if len(set(container_refs)) != len(container_refs) or any(item not in self.counts for item in container_refs):
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

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
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
            if arguments:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            lens = self.context.delivery_lens
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
                region_ref = region.public_ref
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
            action,
            region_ref,
            query,
            page_cursor,
            result,
        )
        public_arguments: Mapping[str, object]
        if tool_name == GroundedLocalToolName.READ_REGION.value:
            public_arguments = {"region_ref": region_ref}
        elif tool_name == GroundedLocalToolName.SEARCH_PAGE_CONTENT.value:
            public_arguments = {"query": query}
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
        return result_type(
            context_id,
            tool_name,
            public_arguments,
            public_result,
            tool_call_id,
            delivery_lens=lens,
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
    action,
    region_ref,
    query,
    page_cursor,
    result,
):
    if isinstance(result, Opened):
        region = region_index.resolve_public_ref(region_ref)
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
            query[:120],
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
    if delivery.manifest.world_observation_id != getattr(
        context.current_observation,
        "observation_id",
        delivery.manifest.world_observation_id,
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
            context.complete_actions,
            context_id=context.context_id,
        )
    )

    form_fields = _current_form_field_bindings(context, delivery.manifest)
    if form_fields:
        form_keys = tuple(sorted(form_fields))
        target_refs = tuple(sorted({target_ref for form in form_fields.values() for target_ref, _ in form}))
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.SET_FORM_FIELDS.value,
                    "Update two to four editable fields in one current form; never submits the form.",
                    _object_schema(
                        {
                            "form": {
                                "type": "string",
                                "description": "one current form scope",
                                "enum": list(form_keys),
                            },
                            "fields": {
                                "type": "array",
                                "description": "ordered field updates within that form",
                                "items": _object_schema(
                                    {
                                        "target": {"type": "string", "enum": list(target_refs)},
                                        "operation": {
                                            "type": "string",
                                            "enum": ["type_text", "select_option"],
                                        },
                                        "value": {"type": "string"},
                                    },
                                    ("target", "operation", "value"),
                                ),
                                "minItems": 2,
                                "maxItems": 4,
                            },
                        },
                        ("form", "fields"),
                    ),
                ),
                _SetFormFieldsBinding(form_fields),
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
                                "items": {"type": "string", "pattern": "^[EN][1-9][0-9]{0,2}$"},
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
                                    "pattern": "^F[1-9][0-9]{0,3}$",
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
                        {item.key: item for item in context.working_facts},
                        context.current_step_index,
                    ),
                )
            )

    registered.extend(
        (
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.READ_REGION.value,
                    "Open one known current PageMap region for readable content; no browser action.",
                    _object_schema(
                        {
                            "region_ref": {
                                "type": "string",
                                "description": "current PageMap R-ref",
                                "pattern": "^R[1-9][0-9]{0,3}$",
                            }
                        },
                        ("region_ref",),
                    ),
                ),
                _WorldReadBinding(context, "region"),
            ),
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
                                "maxLength": 120,
                            }
                        },
                        ("query",),
                    ),
                ),
                _FindControlsBinding(),
            ),
        )
    )
    if (
        context.delivery_lens is not None
        and context.delivery_lens.world_observation_id == getattr(context.current_observation, "observation_id", "")
        and context.delivery_lens.next_cursor
    ):
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.READ_NEXT_PAGE.value,
                    "Continue the prior World read; Runtime owns paging.",
                    _object_schema({}),
                ),
                _WorldReadBinding(context, "continue"),
            )
        )
    if context.actions.next_cursor:
        registered.append(
            RegisteredGroundedTool(
                ToolSpec(
                    GroundedLocalToolName.ACTION_RESULTS_NEXT_PAGE.value,
                    "Continue current action results; Runtime owns paging.",
                    _object_schema({}),
                ),
                _ActionResultsNextPageBinding(
                    context.actions.active_query,
                    context.actions.active_target_filter,
                    context.actions.active_relevance_filter,
                    context.actions.next_cursor,
                ),
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
                            "items": {"type": "string", "pattern": "^F[1-9][0-9]{0,3}$"},
                            "maxItems": 32,
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


def _current_form_field_bindings(
    context: AgentContext,
    manifest: DeliveryManifest,
) -> dict[str, dict[tuple[str, str], _FormFieldAction]]:
    """Group current editable action refs by their nearest explicit form/search node."""

    paths: dict[str, tuple[ActorWorldNodeView, ...]] = {}

    def visit(node: ActorWorldNodeView, parents: tuple[ActorWorldNodeView, ...]) -> None:
        path = (*parents, node)
        paths[node.ref] = path
        for child in node.children:
            visit(child, path)

    for document in context.actor_world.documents:
        for root in document.roots:
            visit(root, ())

    grouped: dict[tuple[str, str], dict[tuple[str, str], _FormFieldAction]] = {}
    for option in context.complete_actions:
        if (
            option.operation not in {"type_text", "select_option"}
            or not option.target_ref
            or not manifest.admits_executable(option.target_ref)
        ):
            continue
        path = paths.get(option.target_ref, ())
        container = next(
            (node for node in reversed(path[:-1]) if node.role.casefold() in {"form", "search"}),
            None,
        )
        if container is None:
            continue
        label = container.label.strip() or container.role
        grouped.setdefault((container.ref, label), {})[(option.target_ref, option.operation)] = _FormFieldAction(
            option.action_id,
            option.operation,
            option.target_ref,
            option.parameter_schema,
        )

    result: dict[str, dict[tuple[str, str], _FormFieldAction]] = {}
    for (container_ref, label), actions in sorted(grouped.items(), key=lambda item: item[0][1].casefold()):
        if len({target for target, _ in actions}) < 2:
            continue
        slug = (
            "-".join(
                part
                for part in "".join(character if character.isalnum() else " " for character in label.casefold()).split()
            )[:48]
            or "fields"
        )
        key = f"form:{slug}"
        if key in result:
            key = f"{key}-{hashlib.sha256(container_ref.encode()).hexdigest()[:8]}"
        result[key] = actions
    return result


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
    if len(specs) > MAX_GROUNDED_TOOL_COUNT or encoded_bytes > MAX_GROUNDED_WORKSPACE_BYTES:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    digest = hashlib.sha256(f"{context.context_id}\0{delivery.delivery_id}\0{encoded}".encode()).hexdigest()[:32]
    catalog_id = f"grounded-catalog:{digest}"
    return GroundedToolCatalog(
        catalog_id,
        context.context_id,
        delivery.delivery_id,
        delivery.manifest,
        delivery.delivery_index,
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
    return GroundedActionResolution(decision)


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
        "pattern": "^(current_world|[EN][1-9][0-9]{0,2})$",
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
