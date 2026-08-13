"""Allowlist grounded workspace compilation and private action resolution."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.agent.decisions import (
    AgentDecisionPackage,
    EstablishAggregateObjective,
    EstablishObjectiveSequence,
    EstablishSetObjective,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    SetPredicateAssessmentDecision,
    SubmitSetPredicateAssessments,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.context import (
    AgentContext,
    AgentGroundingEntityView,
)
from affordance_runtime.model_boundary.contracts import AgentActionOptionView
from affordance_runtime.model_policy.grounded_tool_contracts import (
    MAX_GROUNDED_TOOL_COUNT,
    MAX_GROUNDED_WORKSPACE_BYTES,
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    ToolPolicyView,
)
from affordance_runtime.model_policy.set_objective_catalog import (
    SetCatalogDirective,
    SetCatalogMode,
)
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.task.aggregate_objective import (
    AggregateObjective,
    AggregateOperator,
    AggregateOutputFormat,
    ValueExtractor,
    ValueExtractorKind,
)
from affordance_runtime.task.frontier_contracts import NoObjectiveOperation
from affordance_runtime.task.objective_sequence import (
    SUPPORTED_SEQUENCE_ACTIONS,
    EntitySelector,
    ObjectiveSequence,
    ObjectiveStep,
)
from affordance_runtime.task.predicate_transport import predicate_from_transport
from affordance_runtime.task.set_objective import (
    ActionTemplate,
    FactEquals,
    PredicateTruth,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
    SetQuantifier,
    VisualConcept,
    visual_predicate_leaves,
)
from affordance_runtime.world.schema_validation import validate_value


@dataclass(frozen=True)
class _VerbBinding:
    verb: str
    actions: tuple[tuple[str, str], ...]
    parameter_field: str = ""


@dataclass(frozen=True)
class _NextActionsBinding:
    query: str
    target_id: str
    relevance_role: str
    cursor: str


@dataclass(frozen=True)
class _ObserveBinding:
    modality: str
    assurance: str


@dataclass(frozen=True)
class _SetFactBinding:
    semantic_action: str
    field_name: str
    candidate_target_ids: tuple[str, ...]


@dataclass(frozen=True)
class _EntityObjectiveBinding:
    semantic_action: str
    actions: tuple[tuple[str, str, str], ...]
    parameter_field: str = ""


@dataclass(frozen=True)
class _ObjectiveActionBinding:
    action_id: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class _SetVisualBinding:
    semantic_action: str
    candidates_by_role: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class _SetAssessmentBinding:
    predicate_digest: str
    refs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _SequenceBinding:
    semantic_actions: tuple[str, ...] = SUPPORTED_SEQUENCE_ACTIONS


@dataclass(frozen=True)
class _CompoundSetBinding:
    semantic_actions: tuple[str, ...]
    targets_by_ref: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _AggregateBinding:
    parameter_fields: tuple[tuple[str, str, AggregateOutputFormat], ...]
    targets_by_ref: tuple[tuple[str, str], ...]


def compile_grounded_tool_catalog(context: AgentContext) -> GroundedToolCatalog:
    if context.actions.options and (not context.grounding.entities or not context.grounding.target_refs):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref_by_target = dict(context.grounding.target_refs)
    entity_by_ref = {item.ref: item for item in context.grounding.entities}
    set_directive = _projected_set_directive(context) if context.set_control is not None else None
    allowed_action_ids = set_directive.allowed_action_ids if set_directive is not None else None
    target_filter = ""
    if set_directive is not None and set_directive.mode is SetCatalogMode.MEMBER_ACTIONS_ONLY:
        admitted_targets = tuple(
            option.target_id
            for option in context.actions.options
            if option.action_id in set_directive.allowed_action_ids
        )
        target_filter = admitted_targets[0] if len(set(admitted_targets)) == 1 else ""
    if set_directive is None or set_directive.mode in {
        SetCatalogMode.MEMBER_ACTIONS_ONLY,
        SetCatalogMode.SUCCESSOR_ACTIONS,
    }:
        _reject_ambiguous_unmarked_targets(
            context,
            ref_by_target,
            entity_by_ref,
            target_filter=target_filter,
        )
    settled_effects = _settled_parameter_effects(context, ref_by_target, entity_by_ref)

    grouped: dict[tuple[str, str], list[tuple[str, AgentActionOptionView]]] = {}
    for option in context.actions.options:
        if allowed_action_ids is not None and option.action_id not in allowed_action_ids:
            continue
        if (option.target_id, option.semantic_action) in settled_effects:
            continue
        ref = ref_by_target.get(option.target_id)
        if ref is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        verb = _verb(option.semantic_action)
        shape = _shape_key(verb, option.parameter_schema)
        grouped.setdefault((verb, shape), []).append((ref, option))

    specs: list[ToolSpec] = []
    bindings: list[object] = []
    semantic_ingress = (
        set_directive is not None
        and set_directive.mode is SetCatalogMode.CONTROL_ONLY
        and context.set_control is not None
        and context.set_control.semantic_mode in {"semantic_ingress", "objective_transition"}
    )
    objective_candidate_ids = (
        set(context.set_control.objective_candidate_action_ids)
        if context.set_control is not None and context.set_control.semantic_mode == "objective_transition"
        else {item.action_id for item in context.actions.options}
    )
    unique_grounded_ingress = semantic_ingress and len(objective_candidate_ids) == 1
    seen_modalities: set[str] = set()
    for capability in () if unique_grounded_ingress else context.world.observation_capabilities:
        if capability.modality in seen_modalities:
            continue
        seen_modalities.add(capability.modality)
        specs.append(
            ToolSpec(
                f"observe_{capability.modality}",
                f"Acquire a fresh {capability.modality} observation at {capability.assurance} assurance.",
                _object_schema({}),
            )
        )
        bindings.append(_ObserveBinding(capability.modality, capability.assurance))
    _append_set_assessment_tool(context, ref_by_target, specs, bindings)
    if semantic_ingress and context.set_control is not None and context.set_control.semantic_mode == "semantic_ingress":
        _append_objective_sequence_tool(context, specs, bindings)
    if semantic_ingress and not unique_grounded_ingress:
        _append_compound_set_objective_tool(context, specs, bindings)
        _append_aggregate_objective_tool(context, specs, bindings)
    if (set_directive is None or semantic_ingress) and not context.actions.truncated and not context.actions.has_more:
        _append_set_objective_tools(
            context,
            ref_by_target,
            entity_by_ref,
            specs,
            bindings,
        )
    if (
        set_directive is not None
        and set_directive.mode is SetCatalogMode.MEMBER_ACTIONS_ONLY
        and len(grouped) == 1
        and sum(len(items) for items in grouped.values()) == 1
        and context.set_control is not None
    ):
        ((_shape, values),) = grouped.items()
        _ref, option = values[0]
        specs.append(
            ToolSpec(
                "execute_objective",
                "Execute the one action authorized by the admitted typed objective.",
                _object_schema({}),
            )
        )
        bindings.append(
            _ObjectiveActionBinding(
                option.action_id,
                context.set_control.objective_parameters,
            )
        )
        grouped.clear()
    verb_counts: dict[str, int] = {}
    for (verb, _shape), values in grouped.items():
        verb_counts[verb] = verb_counts.get(verb, 0) + 1
        suffix = "" if verb_counts[verb] == 1 else f"_{verb_counts[verb]}"
        name = f"{verb}{suffix}"
        refs = [ref for ref, _option in values]
        schema, parameter_field = _verb_schema(verb, refs, values[0][1].parameter_schema)
        description = _tool_description(verb, refs, entity_by_ref)
        if set_directive is not None and set_directive.mode is SetCatalogMode.MEMBER_ACTIONS_ONLY and len(values) == 1:
            description = f"{verb} the next member admitted by the current quantified objective."
        specs.append(
            ToolSpec(
                name,
                description,
                schema,
            )
        )
        bindings.append(
            _VerbBinding(
                verb,
                tuple((ref, option.action_id) for ref, option in values),
                parameter_field,
            )
        )

    if context.actions.has_more:
        specs.append(
            ToolSpec(
                "next_actions",
                "Inspect the next in-memory page of currently legal actions.",
                _object_schema({}),
            )
        )
        bindings.append(
            _NextActionsBinding(
                context.actions.active_query,
                context.actions.active_target_filter,
                context.actions.active_relevance_filter,
                context.actions.next_cursor,
            )
        )
    if not specs:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)

    view = ToolPolicyView(
        _task_brief(context),
        tuple(_grounding_entity(item) for item in context.grounding.entities),
        _current_state(context, ref_by_target),
        _previous_result(context, ref_by_target),
        tuple(specs),
    )
    public = {
        "task_brief": view.task_brief,
        "grounding_index": view.grounding_index,
        "current_state": view.current_state,
        "previous_tool_result": view.previous_tool_result,
        "tools": tuple(
            {
                "name": item.name,
                "description": item.description,
                "input_schema": to_json_compatible(item.input_schema),
            }
            for item in specs
        ),
    }
    encoded = json.dumps(
        to_json_compatible(public),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    encoded_bytes = len(encoded.encode())
    if len(specs) > MAX_GROUNDED_TOOL_COUNT or encoded_bytes > MAX_GROUNDED_WORKSPACE_BYTES:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    digest = hashlib.sha256(f"{context.context_id}\0{encoded}".encode()).hexdigest()[:32]
    return GroundedToolCatalog(
        f"grounded-catalog:{digest}",
        context.context_id,
        tuple(specs),
        tuple(bindings),
        view,
        encoded_bytes,
    )


def _projected_set_directive(context: AgentContext) -> SetCatalogDirective:
    control = context.set_control
    if control is None:
        raise ValueError("set control projection is absent")
    return SetCatalogDirective(
        SetCatalogMode(control.mode),
        frozenset(control.allowed_action_ids),
        control.reason_code,
    )


def _append_set_objective_tools(
    context: AgentContext,
    ref_by_target: Mapping[str, str],
    entity_by_ref: Mapping[str, AgentGroundingEntityView],
    specs: list[ToolSpec],
    bindings: list[object],
) -> None:
    """Compile typed semantic ingress from the current public action/fact schemas."""

    mandatory = bool(
        context.set_control is not None
        and context.set_control.semantic_mode in {"semantic_ingress", "objective_transition"}
    )
    candidate_action_ids = (
        set(context.set_control.objective_candidate_action_ids)
        if context.set_control is not None and context.set_control.semantic_mode == "objective_transition"
        else None
    )
    options_by_action: dict[tuple[str, str], list[AgentActionOptionView]] = {}
    for option in context.actions.options:
        if candidate_action_ids is not None and option.action_id not in candidate_action_ids:
            continue
        verb = _verb(option.semantic_action)
        options_by_action.setdefault(
            (option.semantic_action, _shape_key(verb, option.parameter_schema)),
            [],
        ).append(option)
    unique_ingress = mandatory and sum(len(items) for items in options_by_action.values()) == 1
    verb_groups: dict[str, int] = {}
    for (semantic_action, _shape), options in options_by_action.items():
        verb = _verb(semantic_action)
        verb_groups[verb] = verb_groups.get(verb, 0) + 1
        suffix = "" if verb_groups[verb] == 1 else f"_{verb_groups[verb]}"
        entity_values = []
        for option in options:
            ref = ref_by_target.get(option.target_id)
            if ref is None:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
            entity_values.append((ref, option.action_id, option.target_id))
        entity_schema, parameter_field = _verb_schema(
            verb,
            tuple(item[0] for item in entity_values),
            options[0].parameter_schema,
        )
        if mandatory:
            specs.append(
                ToolSpec(
                    f"establish_{verb}_entity_objective{suffix}",
                    (
                        f"Establish one typed {verb} objective for an explicitly identified current "
                        "E-ref. Do not use this for quantified sets, derived values, public-fact "
                        "selection, or ordered future steps. This performs no GUI action."
                    ),
                    entity_schema,
                )
            )
            bindings.append(
                _EntityObjectiveBinding(
                    semantic_action,
                    tuple(entity_values),
                    parameter_field,
                )
            )
        if options[0].parameter_schema.get("required") or options[0].parameter_schema.get("properties"):
            continue
        if unique_ingress:
            continue
        action_roles = {entity_by_ref[ref_by_target[option.target_id]].role.casefold().strip() for option in options}
        candidates_by_role: dict[str, list[str]] = {}
        fields_by_role: dict[str, dict[str, list[object]]] = {}
        # Scope enumeration is independent of actionability.  A TRUE visual
        # entity without a current action route must remain in the universe so
        # the controller can fail closed instead of certifying a filtered set.
        for target_id, ref in ref_by_target.items():
            entity = entity_by_ref.get(ref)
            if entity is None:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
            role = entity.role.casefold().strip()
            if role not in action_roles:
                continue
            candidates_by_role.setdefault(role, []).append(target_id)
            for field_name, value in entity.state.items():
                if not _set_fact_value(value):
                    continue
                values = fields_by_role.setdefault(role, {}).setdefault(field_name, [])
                if value not in values:
                    values.append(value)
        fact_index = 0
        for role, fields in sorted(fields_by_role.items()):
            role_candidates = tuple(candidates_by_role.get(role, ()))
            if not mandatory and len(role_candidates) < 2:
                continue
            for field_name, observed_values in sorted(fields.items()):
                fact_index += 1
                value_schema = _fact_value_schema(tuple(observed_values))
                if value_schema is None:
                    continue
                fields_schema = {
                    "value": value_schema,
                    "quantifier": {
                        "type": "string",
                        "enum": [
                            SetQuantifier.EXACTLY_ONE.value,
                            SetQuantifier.ALL_IN_CLOSED_SCOPE.value,
                        ],
                    },
                }
                specs.append(
                    ToolSpec(
                        _fact_objective_tool_name(verb, role, field_name, fact_index),
                        (
                            f'Establish a typed {verb} objective where public fact "{field_name}" '
                            f'for candidate role "{role}" equals the supplied value. '
                            "This performs no GUI action."
                        ),
                        _object_schema(fields_schema, ("value", "quantifier")),
                    )
                )
                bindings.append(
                    _SetFactBinding(
                        semantic_action,
                        field_name,
                        role_candidates,
                    )
                )
        roles = tuple(
            (role, tuple(target_ids))
            for role, target_ids in sorted(candidates_by_role.items())
            if target_ids and (mandatory or len(target_ids) >= 2)
        )
        if roles:
            specs.append(
                ToolSpec(
                    f"establish_{verb}_visual_objective",
                    (
                        "Use before any member action when the task selects a quantified set or an "
                        "open-vocabulary visual concept not represented by any public fact. Never "
                        "replace an available public fact with this tool. Establishes "
                        "the objective over one typed candidate role and performs no GUI action."
                    ),
                    _object_schema(
                        {
                            "candidate_role": {"type": "string", "enum": [item[0] for item in roles]},
                            "concept": {"type": "string", "minLength": 1, "maxLength": 160},
                            "quantifier": {
                                "type": "string",
                                "enum": [
                                    SetQuantifier.EXACTLY_ONE.value,
                                    SetQuantifier.ALL_IN_CLOSED_SCOPE.value,
                                ],
                            },
                        },
                        ("candidate_role", "concept", "quantifier"),
                    ),
                )
            )
            bindings.append(_SetVisualBinding(semantic_action, roles))


def _append_objective_sequence_tool(
    context: AgentContext,
    specs: list[ToolSpec],
    bindings: list[object],
) -> None:
    """Offer a bounded future-resolvable plan without future identities."""

    semantic_actions = SUPPORTED_SEQUENCE_ACTIONS
    selector_schema = _predicate_transport_schema()
    step_schema = _object_schema(
        {
            "predicate": selector_schema,
            "semantic_action": {"type": "string", "enum": list(semantic_actions)},
            "parameters": {"type": "object", "additionalProperties": True},
            "postcondition_predicate": {"anyOf": [selector_schema, {"type": "null"}]},
        },
        (
            "predicate",
            "semantic_action",
            "parameters",
            "postcondition_predicate",
        ),
    )
    specs.append(
        ToolSpec(
            "establish_objective_sequence",
            (
                "Use for an explicit ordered multi-step instruction, especially when later controls "
                "appear after earlier effects. Establish 1-8 typed future-resolvable GUI steps. Each predicate is "
                "re-evaluated after a fresh observation; use public fields such as "
                "identity.label and never future E-refs or coordinates. Performs no action."
            ),
            _object_schema(
                {
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": step_schema,
                    }
                },
                ("steps",),
            ),
        )
    )
    bindings.append(_SequenceBinding())


def _append_compound_set_objective_tool(
    context: AgentContext,
    specs: list[ToolSpec],
    bindings: list[object],
) -> None:
    actions = tuple(
        sorted(
            {
                option.semantic_action
                for option in context.actions.options
                if not option.parameter_schema.get("required") and not option.parameter_schema.get("properties")
            }
        )
    )
    if not actions:
        return
    specs.append(
        ToolSpec(
            "establish_compound_set_objective",
            (
                "Establish a scope-relative quantified objective from a bounded boolean "
                "predicate. Runtime owns candidate enumeration and completion; this performs no action."
            ),
            _object_schema(
                {
                    "predicate": _predicate_transport_schema(),
                    "quantifier": {
                        "type": "string",
                        "enum": [
                            SetQuantifier.EXACTLY_ONE.value,
                            SetQuantifier.ALL_IN_CLOSED_SCOPE.value,
                        ],
                    },
                    "semantic_action": {"type": "string", "enum": list(actions)},
                    "scope_extent": {
                        "type": "string",
                        "enum": [item.value for item in ScopeExtent],
                    },
                    "scope_root": {
                        "type": "string",
                        "enum": ["current-viewport", *[item.ref for item in context.grounding.entities]],
                    },
                },
                ("predicate", "quantifier", "semantic_action", "scope_extent", "scope_root"),
            ),
        )
    )
    bindings.append(
        _CompoundSetBinding(
            actions,
            tuple(sorted((ref, target_id) for target_id, ref in context.grounding.target_refs.items())),
        )
    )


def _append_aggregate_objective_tool(
    context: AgentContext,
    specs: list[ToolSpec],
    bindings: list[object],
) -> None:
    parameter_fields: dict[str, tuple[str, AggregateOutputFormat]] = {}
    for option in context.actions.options:
        properties = option.parameter_schema.get("properties")
        required = option.parameter_schema.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, tuple | list):
            continue
        if len(required) == 1 and required[0] in properties:
            field_name = str(required[0])
            field_schema = properties[field_name]
            field_type = field_schema.get("type") if isinstance(field_schema, Mapping) else None
            parameter_fields.setdefault(
                option.semantic_action,
                (
                    field_name,
                    AggregateOutputFormat.NUMBER
                    if field_type in {"integer", "number"}
                    else AggregateOutputFormat.INTEGER_STRING,
                ),
            )
    if not parameter_fields:
        return
    specs.append(
        ToolSpec(
            "establish_aggregate_objective",
            (
                "Required when the task asks to derive COUNT/SUM/MIN/MAX. Derive it from a closed source scope and write the Runtime-derived "
                "value to one destination. Never provide the result value yourself."
            ),
            _object_schema(
                {
                    "source_predicate": _predicate_transport_schema(),
                    "operator": {
                        "type": "string",
                        "enum": [item.value for item in AggregateOperator],
                    },
                    "value_field": {"type": "string", "maxLength": 120},
                    "destination_predicate": _predicate_transport_schema(),
                    "semantic_action": {
                        "type": "string",
                        "enum": sorted(parameter_fields),
                    },
                    "scope_extent": {
                        "type": "string",
                        "enum": [item.value for item in ScopeExtent],
                    },
                    "scope_root": {
                        "type": "string",
                        "enum": ["current-viewport", *[item.ref for item in context.grounding.entities]],
                    },
                },
                (
                    "source_predicate",
                    "operator",
                    "value_field",
                    "destination_predicate",
                    "semantic_action",
                    "scope_extent",
                    "scope_root",
                ),
            ),
        )
    )
    bindings.append(
        _AggregateBinding(
            tuple((action, field, output) for action, (field, output) in sorted(parameter_fields.items())),
            tuple(sorted((ref, target_id) for target_id, ref in context.grounding.target_refs.items())),
        )
    )


def _predicate_transport_schema(*, include_visual: bool = True) -> dict[str, object]:
    atoms = [
        _object_schema(
            {
                "kind": {"type": "string", "const": "fact_equals"},
                "field_name": {"type": "string", "minLength": 1, "maxLength": 120},
                "expected": {},
                "negated": {"type": "boolean"},
            },
            ("kind", "field_name", "expected", "negated"),
        ),
        _object_schema(
            {
                "kind": {"type": "string", "const": "compare"},
                "field_name": {"type": "string", "minLength": 1, "maxLength": 120},
                "operator": {
                    "type": "string",
                    "enum": ["eq", "ne", "lt", "lte", "gt", "gte", "in"],
                },
                "expected": {},
                "negated": {"type": "boolean"},
            },
            ("kind", "field_name", "operator", "expected", "negated"),
        ),
    ]
    if include_visual:
        atoms.extend(
            [
                _object_schema(
                    {
                        "kind": {"type": "string", "const": "visual_concept"},
                        "text": {"type": "string", "minLength": 1, "maxLength": 160},
                        "negated": {"type": "boolean"},
                    },
                    ("kind", "text", "negated"),
                ),
                _object_schema(
                    {
                        "kind": {"type": "string", "const": "visual_attribute"},
                        "text": {"type": "string", "minLength": 1, "maxLength": 160},
                        "negated": {"type": "boolean"},
                    },
                    ("kind", "text", "negated"),
                ),
            ]
        )
    atom_schema = {"oneOf": atoms}
    return _object_schema(
        {
            "any_of": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": _object_schema(
                    {
                        "all_of": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": atom_schema,
                        }
                    },
                    ("all_of",),
                ),
            }
        },
        ("any_of",),
    )


def _append_set_assessment_tool(
    context: AgentContext,
    ref_by_target: Mapping[str, str],
    specs: list[ToolSpec],
    bindings: list[object],
) -> None:
    """Expose one complete E-ref classification batch for current UNKNOWNs."""

    control = context.set_control
    if control is None or not control.unknown_target_ids:
        return
    refs = tuple(
        (ref_by_target[target_id], target_id) for target_id in control.unknown_target_ids if target_id in ref_by_target
    )
    if len(refs) != len(control.unknown_target_ids):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    properties = {
        ref: {
            "type": "string",
            "enum": [
                PredicateTruth.TRUE.value,
                PredicateTruth.FALSE.value,
                PredicateTruth.UNKNOWN.value,
            ],
        }
        for ref, _target_id in refs
    }
    specs.append(
        ToolSpec(
            "classify_set_candidates",
            (
                "Classify every listed E-ref against the current typed visual predicate. "
                "This supplies semantic evidence only and performs no action."
            ),
            _object_schema(properties, tuple(properties)),
        )
    )
    bindings.append(_SetAssessmentBinding(control.predicate_digest, refs))


def _set_fact_value(value: object) -> bool:
    if value is None or isinstance(value, bool | int | float):
        return True
    if isinstance(value, str):
        return bool(value.strip()) and len(value) <= 80
    if isinstance(value, Mapping):
        encoded = json.dumps(
            to_json_compatible(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return len(encoded) <= 160
    return False


def _fact_value_schema(values: tuple[object, ...]) -> dict[str, object] | None:
    """Infer one bounded JSON schema from current public values, never exact-value strings."""

    if not values:
        return None
    if all(isinstance(item, bool) for item in values):
        return {"type": "boolean"}
    if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
        return {"type": "integer"}
    if all(isinstance(item, int | float) and not isinstance(item, bool) for item in values):
        return {"type": "number"}
    if all(isinstance(item, str) for item in values):
        choices = sorted({str(item) for item in values})
        schema: dict[str, object] = {"type": "string", "maxLength": 80}
        if len(choices) <= 32:
            schema["enum"] = choices
        return schema
    if all(isinstance(item, Mapping) for item in values):
        mappings = tuple(dict(item) for item in values)
        keys = set(mappings[0])
        if any(set(item) != keys for item in mappings):
            return None
        properties = {}
        for key in sorted(keys):
            if not isinstance(key, str):
                return None
            child = _fact_value_schema(tuple(item[key] for item in mappings))
            if child is None:
                return None
            properties[key] = child
        return _object_schema(properties, tuple(properties))
    return None


def _fact_objective_tool_name(
    verb: str,
    role: str,
    field_name: str,
    index: int,
) -> str:
    role_token = re.sub(r"[^a-z0-9]+", "_", role.casefold()).strip("_") or "entity"
    field_token = re.sub(r"[^a-z0-9]+", "_", field_name.casefold()).strip("_") or "fact"
    value = f"establish_{verb}_{role_token}_where_{field_token}_equals"
    if len(value) <= 64:
        return value
    digest = hashlib.sha256(f"{field_name}\0{index}".encode()).hexdigest()[:8]
    return f"{value[:55]}_{digest}"


def resolve_grounded_tool_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> AgentDecisionPackage:
    if catalog.context_id != expected_context_id or (
        expected_catalog_id is not None and catalog.catalog_id != expected_catalog_id
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
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
    if isinstance(binding, _NextActionsBinding):
        decision = RequestActionPage(
            expected_context_id,
            binding.query,
            binding.target_id,
            binding.relevance_role,
            binding.cursor,
        )
        return AgentDecisionPackage(NoObjectiveOperation(), decision)
    if isinstance(binding, _ObserveBinding):
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            RequestObservation(
                expected_context_id,
                "current_world",
                binding.modality,
                binding.assurance,
                f"acquire fresh {binding.modality} grounding",
            ),
        )
    if isinstance(binding, _ObjectiveActionBinding):
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            SelectAction(
                expected_context_id,
                binding.action_id,
                dict(binding.parameters),
                "",
            ),
        )
    if isinstance(binding, _SequenceBinding):
        raw_steps = call.arguments.get("steps")
        if not isinstance(raw_steps, tuple | list):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        steps = []
        for index, raw in enumerate(raw_steps):
            if not isinstance(raw, Mapping):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            semantic_action = str(raw["semantic_action"])
            if semantic_action not in binding.semantic_actions:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            selector = raw["predicate"]
            postcondition = raw.get("postcondition_predicate")
            if not isinstance(selector, Mapping) or (
                postcondition is not None and not isinstance(postcondition, Mapping)
            ):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            steps.append(
                ObjectiveStep(
                    f"step:{index + 1}",
                    EntitySelector(predicate_from_transport(selector)),
                    ActionTemplate(semantic_action, parameters=dict(raw["parameters"])),
                    (
                        EntitySelector(predicate_from_transport(postcondition))
                        if isinstance(postcondition, Mapping)
                        else None
                    ),
                )
            )
        digest = hashlib.sha256(
            json.dumps(
                [
                    {
                        "predicate": to_json_compatible(raw["predicate"]),
                        "semantic_action": raw["semantic_action"],
                        "parameters": to_json_compatible(raw["parameters"]),
                        "postcondition_predicate": to_json_compatible(raw.get("postcondition_predicate")),
                    }
                    for raw in raw_steps
                ],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()[:24]
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishObjectiveSequence(
                expected_context_id,
                ObjectiveSequence(f"sequence:{digest}", tuple(steps)),
            ),
        )
    if isinstance(binding, _CompoundSetBinding):
        semantic_action = str(call.arguments["semantic_action"])
        if semantic_action not in binding.semantic_actions:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        root = str(call.arguments["scope_root"])
        root_target = "current-viewport" if root == "current-viewport" else dict(binding.targets_by_ref).get(root, "")
        if not root_target:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishSetObjective(
                expected_context_id,
                predicate_from_transport(call.arguments["predicate"]),
                SetQuantifier(str(call.arguments["quantifier"])),
                semantic_action,
                (),
                {},
                ScopeExtent(str(call.arguments["scope_extent"])),
                root_target,
            ),
        )
    if isinstance(binding, _AggregateBinding):
        semantic_action = str(call.arguments["semantic_action"])
        fields = {action: (field, output) for action, field, output in binding.parameter_fields}
        if semantic_action not in fields:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        operator = AggregateOperator(str(call.arguments["operator"]))
        value_field = str(call.arguments["value_field"])
        if operator is not AggregateOperator.COUNT and not value_field:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        root = str(call.arguments["scope_root"])
        root_target = "current-viewport" if root == "current-viewport" else dict(binding.targets_by_ref).get(root, "")
        if not root_target:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        member = predicate_from_transport(call.arguments["source_predicate"])
        destination = predicate_from_transport(call.arguments["destination_predicate"])
        parameter_name, output_format = fields[semantic_action]
        payload = {
            "source": to_json_compatible(call.arguments["source_predicate"]),
            "operator": operator.value,
            "value_field": value_field,
            "destination": to_json_compatible(call.arguments["destination_predicate"]),
            "semantic_action": semantic_action,
            "scope_extent": call.arguments["scope_extent"],
            "scope_root": root_target,
        }
        digest = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()[:24]
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishAggregateObjective(
                expected_context_id,
                AggregateObjective(
                    f"aggregate-objective:{digest}",
                    ScopeSpec(
                        f"scope:{digest}",
                        root_target,
                        ScopeExtent(str(call.arguments["scope_extent"])),
                        entity_domain=(
                            ScopeEntityDomain.ALL_VISIBLE
                            if visual_predicate_leaves(member)
                            else ScopeEntityDomain.STRUCTURED
                        ),
                    ),
                    member,
                    ValueExtractor(
                        ValueExtractorKind.CONSTANT if operator is AggregateOperator.COUNT else ValueExtractorKind.FACT,
                        value_field,
                        1,
                    ),
                    operator,
                    destination,
                    semantic_action,
                    parameter_name,
                    output_format,
                ),
            ),
        )
    if isinstance(binding, _EntityObjectiveBinding):
        ref = str(call.arguments.get("target") or "")
        actions = {item[0]: item for item in binding.actions}
        if not ref and len(binding.actions) == 1:
            ref = binding.actions[0][0]
        if ref not in actions:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        _ref, _action_id, target_id = actions[ref]
        parameters = {}
        if binding.parameter_field:
            parameters["value"] = call.arguments[binding.parameter_field]
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishSetObjective(
                expected_context_id,
                FactEquals("identity.entity_id", target_id),
                SetQuantifier.EXACTLY_ONE,
                binding.semantic_action,
                (target_id,),
                parameters,
            ),
        )
    if isinstance(binding, _SetFactBinding):
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishSetObjective(
                expected_context_id,
                FactEquals(binding.field_name, call.arguments["value"]),
                SetQuantifier(str(call.arguments["quantifier"])),
                binding.semantic_action,
                binding.candidate_target_ids,
            ),
        )
    if isinstance(binding, _SetVisualBinding):
        role = str(call.arguments["candidate_role"])
        candidates = dict(binding.candidates_by_role)[role]
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            EstablishSetObjective(
                expected_context_id,
                VisualConcept(str(call.arguments["concept"])),
                SetQuantifier(str(call.arguments["quantifier"])),
                binding.semantic_action,
                candidates,
            ),
        )
    if isinstance(binding, _SetAssessmentBinding):
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            SubmitSetPredicateAssessments(
                expected_context_id,
                binding.predicate_digest,
                tuple(
                    SetPredicateAssessmentDecision(
                        target_id,
                        PredicateTruth(str(call.arguments[ref])),
                        None,
                    )
                    for ref, target_id in binding.refs
                ),
            ),
        )
    assert isinstance(binding, _VerbBinding)
    ref = str(call.arguments.get("target") or "")
    actions = dict(binding.actions)
    if not ref and len(binding.actions) == 1:
        ref = binding.actions[0][0]
    if ref not in actions:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    parameters = {}
    if binding.parameter_field:
        parameters["value"] = call.arguments[binding.parameter_field]
    return AgentDecisionPackage(
        NoObjectiveOperation(),
        SelectAction(expected_context_id, actions[ref], parameters, ""),
    )


def _reject_ambiguous_unmarked_targets(
    context: AgentContext,
    ref_by_target: Mapping[str, str],
    entity_by_ref: Mapping[str, AgentGroundingEntityView],
    *,
    target_filter: str = "",
) -> None:
    actionable: list[tuple[str, AgentGroundingEntityView]] = []
    for option in context.actions.options:
        if target_filter and option.target_id != target_filter:
            continue
        ref = ref_by_target.get(option.target_id)
        entity = entity_by_ref.get(ref or "")
        if entity is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        actionable.append((option.semantic_action, entity))
    signatures: dict[tuple[object, ...], list[AgentGroundingEntityView]] = {}
    for semantic_action, entity in actionable:
        signature = (
            semantic_action,
            entity.role,
            entity.label.casefold().strip(),
            json.dumps(to_json_compatible(entity.state), sort_keys=True, separators=(",", ":")),
            entity.relation_hints,
        )
        signatures.setdefault(signature, []).append(entity)
    if any(len(values) > 1 and not all(item.marked for item in values) for values in signatures.values()):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.GROUNDING_GAP)


def _settled_parameter_effects(
    context: AgentContext,
    ref_by_target: Mapping[str, str],
    entity_by_ref: Mapping[str, AgentGroundingEntityView],
) -> set[tuple[str, str]]:
    """Hide a confirmed current fill/select from the next model tool menu.

    Runtime legality is unchanged.  This removes only a model-facing duplicate
    while the exact value produced by the previous action is still observable.
    Explicit repair/strategy feedback reopens the operation.
    """

    feedback = context.control_feedback
    if feedback is not None and (
        feedback.strategy_transition_required
        or (feedback.recovery is not None and feedback.recovery.strategy_change_required)
    ):
        return set()
    settled: set[tuple[str, str]] = set()
    inspected: set[tuple[str, str]] = set()
    for turn in reversed(context.history.items):
        key = (turn.target_id, turn.semantic_action)
        if key in inspected or turn.semantic_action not in {"fill", "select"}:
            continue
        inspected.add(key)
        if str(turn.dispatch_status) != "sent" or str(turn.action_evaluation_status) != "effect_confirmed":
            continue
        requested = turn.public_parameters.get("value")
        ref = ref_by_target.get(turn.target_id)
        entity = entity_by_ref.get(ref or "")
        if not isinstance(requested, str) or entity is None:
            continue
        current = entity.state.get("value")
        if current is None and turn.semantic_action == "select":
            current = entity.state.get("selected")
        if current == requested:
            settled.add(key)
    return settled


def _verb(semantic_action: str) -> str:
    return {"activate": "click", "fill": "fill", "select": "select"}.get(semantic_action, semantic_action)


def _tool_description(verb, refs, entity_by_ref) -> str:
    values = []
    for ref in refs:
        entity = entity_by_ref[ref]
        state = ",".join(
            f"{key}={json.dumps(to_json_compatible(value), ensure_ascii=False, separators=(',', ':'))}"
            for key, value in entity.state.items()
            if key in {"value", "selected", "checked", "expanded"}
        )
        relations = ",".join(entity.relation_hints[:2])
        details = ",".join(item for item in (entity.role, repr(entity.label), state, relations) if item)
        values.append(f"{ref}({details})")
    targets = "; ".join(values)
    description = (
        f"{verb} one current target. For a quantified request or a criterion represented by an "
        f"establish_* operation, establish that objective first. Targets: {targets}"
    )
    return description[:500]


def _shape_key(verb: str, schema: Mapping[str, object]) -> str:
    return verb + ":" + json.dumps(to_json_compatible(schema), sort_keys=True, separators=(",", ":"))


def _verb_schema(verb, refs, parameter_schema):
    # A singleton operation already carries one referentially closed Runtime
    # binding.  Requiring the model to echo its sole E-ref adds no choice and is
    # a common source of avoidable schema failures.
    properties: dict[str, object] = {}
    required: list[str] = []
    if len(refs) > 1:
        properties["target"] = {"type": "string", "enum": refs}
        required.append("target")
    parameter_field = ""
    if verb == "fill":
        properties["text"] = {"type": "string"}
        required.append("text")
        parameter_field = "text"
    elif verb == "select":
        value = dict(parameter_schema.get("properties", {})).get("value", {"type": "string"})
        properties["value"] = to_json_compatible(value)
        required.append("value")
        parameter_field = "value"
    elif parameter_schema.get("required"):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return _object_schema(properties, required), parameter_field


def _object_schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _task_brief(context):
    return {
        "instruction": context.task.instruction,
        "constraints": list(context.task.constraints.items),
        "public_inputs": to_json_compatible(context.task.public_inputs),
    }


def _grounding_entity(item):
    return {
        "ref": item.ref,
        "role": item.role,
        "label": item.label,
        "state": to_json_compatible(item.state),
        "relations": list(item.relation_hints),
        "verbs": list(item.verbs),
        "marked": item.marked,
    }


def _current_state(context, ref_by_target):
    frontier = context.progress.task_frontier
    value = {
        "task_status": str(context.progress.validated_task_status),
        "active_objective": context.progress.active_objective,
        "frontier": list(frontier.current_frontier) if frontier is not None else [],
        "verified_public_facts": [
            {
                "subject": ref_by_target.get(item.subject_id, "task"),
                "field": item.predicate,
                "value": to_json_compatible(item.value),
            }
            for item in context.progress.verified_public_facts
        ],
        "remaining_turns": context.budgets.remaining_turns,
        "decision_mode": context.decision_mode.value,
    }
    if context.set_control is not None:
        value["quantified_objective"] = {
            "disposition": context.set_control.disposition,
            "reason": context.set_control.reason_code,
            "candidate_count": context.set_control.candidate_count,
            "matched_count": context.set_control.matched_count,
            "certified": context.set_control.certified,
            "predicate": to_json_compatible(context.set_control.predicate),
            "unknown_candidates": [
                ref_by_target[item] for item in context.set_control.unknown_target_ids if item in ref_by_target
            ],
            "evidence_needs": list(context.set_control.evidence_needs),
        }
    return value


def _previous_result(context, ref_by_target):
    if context.control_feedback is not None:
        feedback = context.control_feedback
        result = {
            "kind": str(feedback.kind),
            "code": feedback.code,
            "source": str(feedback.source),
            "next_decision_disposition": str(feedback.next_decision_disposition),
            "strategy_transition_required": feedback.strategy_transition_required,
            "strategy_change_required": (
                feedback.recovery.strategy_change_required if feedback.recovery is not None else False
            ),
        }
        if feedback.related_decision is not None:
            previous_semantic_action = next(
                (
                    item.semantic_action
                    for item in reversed(context.history.items)
                    if item.target_id == feedback.related_decision.target_id and item.semantic_action
                ),
                "",
            )
            result["related_action"] = {
                "verb": _verb(previous_semantic_action or feedback.related_decision.kind),
                "target": ref_by_target.get(feedback.related_decision.target_id, ""),
                "parameters": to_json_compatible(feedback.related_decision.parameters),
            }
        if feedback.violation is not None:
            result["violation"] = {
                "contract_owner": feedback.violation.contract_owner,
                "code": feedback.violation.code,
                "field_paths": list(feedback.violation.field_paths),
                "expected": to_json_compatible(feedback.violation.expected),
                "actual": to_json_compatible(feedback.violation.actual),
            }
        if feedback.semantic_effect is not None:
            result["semantic_effect"] = {
                "dispatch": feedback.semantic_effect.dispatch,
                "expected_effects": list(feedback.semantic_effect.expected_effects),
                "observed_effect": feedback.semantic_effect.observed_effect,
                "world_changed": feedback.semantic_effect.world_changed,
                "action_space_changed": feedback.semantic_effect.action_space_changed,
                "task_progress_changed": feedback.semantic_effect.task_progress_changed,
                "changed_public_fields": list(feedback.semantic_effect.changed_public_fields),
            }
        if feedback.recovery is not None:
            result["recovery"] = {
                "must_change_fields": list(feedback.recovery.must_change_fields),
                "repeat_previous_decision_allowed": feedback.recovery.repeat_previous_decision_allowed,
                "retry_allowed": feedback.recovery.retry_allowed,
                "rollback_available": feedback.recovery.rollback_available,
                "strategy_change_required": feedback.recovery.strategy_change_required,
            }
        return result
    if not context.history.items:
        return {}
    item = context.history.items[-1]
    return {
        "decision": item.decision_kind,
        "verb": _verb(item.semantic_action) if item.semantic_action else "",
        "target": ref_by_target.get(item.target_id, ""),
        "dispatch": item.dispatch_status,
        "effect": item.action_evaluation_status,
        "task": item.task_evaluation_status,
        "reason": item.reason,
    }
