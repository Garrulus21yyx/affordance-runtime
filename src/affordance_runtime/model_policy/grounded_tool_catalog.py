"""Allowlist grounded workspace compilation and private action resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.agent.decisions import (
    AgentDecisionPackage,
    RequestActionPage,
    RequestObservation,
    SelectAction,
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
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.task.frontier_contracts import NoObjectiveOperation
from affordance_runtime.world.schema_validation import validate_value
from affordance_runtime.world.vision_escalation import (
    requested_color_family,
    requires_multiple_visual_targets,
)


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


def compile_grounded_tool_catalog(context: AgentContext) -> GroundedToolCatalog:
    if context.actions.options and (
        not context.grounding.entities or not context.grounding.target_refs
    ):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref_by_target = dict(context.grounding.target_refs)
    entity_by_ref = {item.ref: item for item in context.grounding.entities}
    _reject_ambiguous_unmarked_targets(context, ref_by_target, entity_by_ref)
    settled_effects = _settled_parameter_effects(context, ref_by_target, entity_by_ref)
    color_family = requested_color_family(context.task.instruction)

    grouped: dict[tuple[str, str], list[tuple[str, AgentActionOptionView]]] = {}
    for option in context.actions.options:
        if (option.target_id, option.semantic_action) in settled_effects:
            continue
        ref = ref_by_target.get(option.target_id)
        if ref is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        verb = _verb(option.semantic_action)
        entity = entity_by_ref.get(ref)
        if (
            verb == "click"
            and entity is not None
            and entity.state.get("selected") is True
            and requires_multiple_visual_targets(context.task.instruction)
        ):
            continue
        if (
            verb == "click"
            and color_family
            and entity is not None
            and not entity.label.strip()
            and entity.state.get("color_family") not in {None, color_family}
        ):
            continue
        shape = _shape_key(verb, option.parameter_schema)
        grouped.setdefault((verb, shape), []).append((ref, option))

    specs: list[ToolSpec] = []
    bindings: list[object] = []
    seen_modalities: set[str] = set()
    for capability in context.world.observation_capabilities:
        if capability.modality in seen_modalities:
            continue
        seen_modalities.add(capability.modality)
        specs.append(ToolSpec(
            f"observe_{capability.modality}",
            f"Acquire a fresh {capability.modality} observation at {capability.assurance} assurance.",
            _object_schema({}),
        ))
        bindings.append(_ObserveBinding(capability.modality, capability.assurance))
    verb_counts: dict[str, int] = {}
    for (verb, _shape), values in grouped.items():
        verb_counts[verb] = verb_counts.get(verb, 0) + 1
        suffix = "" if verb_counts[verb] == 1 else f"_{verb_counts[verb]}"
        name = f"{verb}{suffix}"
        refs = [ref for ref, _option in values]
        schema, parameter_field = _verb_schema(verb, refs, values[0][1].parameter_schema)
        specs.append(ToolSpec(
            name,
            _tool_description(verb, refs, entity_by_ref),
            schema,
        ))
        bindings.append(_VerbBinding(
            verb,
            tuple((ref, option.action_id) for ref, option in values),
            parameter_field,
        ))

    if context.actions.has_more:
        specs.append(ToolSpec(
            "next_actions",
            "Inspect the next in-memory page of currently legal actions.",
            _object_schema({}),
        ))
        bindings.append(_NextActionsBinding(
            context.actions.active_query,
            context.actions.active_target_filter,
            context.actions.active_relevance_filter,
            context.actions.next_cursor,
        ))
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
        "tools": tuple({
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        } for item in specs),
    }
    encoded = json.dumps(
        to_json_compatible(public), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
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
) -> None:
    actionable: list[tuple[str, AgentGroundingEntityView]] = []
    for option in context.actions.options:
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
        or (
            feedback.recovery is not None
            and feedback.recovery.strategy_change_required
        )
    ):
        return set()
    settled: set[tuple[str, str]] = set()
    inspected: set[tuple[str, str]] = set()
    for turn in reversed(context.history.items):
        key = (turn.target_id, turn.semantic_action)
        if key in inspected or turn.semantic_action not in {"fill", "select"}:
            continue
        inspected.add(key)
        if (
            str(turn.dispatch_status) != "sent"
            or str(turn.action_evaluation_status) != "effect_confirmed"
        ):
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
    description = f"{verb} one current target. Targets: {targets}"
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
    return {
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
