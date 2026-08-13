"""Disposable action-only catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.agent.decisions import (
    AgentDecision,
    RequestActionPage,
    RequestObservation,
    SelectAction,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.context import AgentContext, AgentGroundingEntityView
from affordance_runtime.model_boundary.contracts import AgentActionOptionView
from affordance_runtime.model_policy.execution_control_catalog import (
    ExecutionCatalogDirective,
    ExecutionCatalogMode,
)
from affordance_runtime.model_policy.grounded_tool_contracts import (
    MAX_GROUNDED_TOOL_COUNT,
    MAX_GROUNDED_WORKSPACE_BYTES,
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    ToolPolicyView,
)
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.world.schema_validation import validate_value


@dataclass(frozen=True)
class _VerbBinding:
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
class _ObjectiveActionBinding:
    action_id: str
    parameters: Mapping[str, object]


def compile_grounded_tool_catalog(context: AgentContext) -> GroundedToolCatalog:
    if context.actions.options and (not context.grounding.entities or not context.grounding.target_refs):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref_by_target = dict(context.grounding.target_refs)
    entity_by_ref = {item.ref: item for item in context.grounding.entities}
    directive = _projected_execution_directive(context) if context.execution_control is not None else None
    allowed = directive.allowed_action_ids if directive is not None else None
    grouped: dict[tuple[str, str], list[tuple[str, AgentActionOptionView]]] = {}
    for option in context.actions.options:
        if allowed is not None and option.action_id not in allowed:
            continue
        ref = ref_by_target.get(option.target_id)
        if ref is None:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        verb = _verb(option.semantic_action)
        grouped.setdefault((verb, _shape_key(verb, option.parameter_schema)), []).append((ref, option))

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

    if (
        directive is not None
        and directive.mode is ExecutionCatalogMode.MEMBER_ACTIONS_ONLY
        and len(grouped) == 1
        and sum(len(items) for items in grouped.values()) == 1
        and context.execution_control is not None
    ):
        ((_shape, values),) = grouped.items()
        _ref, option = values[0]
        specs.append(ToolSpec(
            "execute_objective",
            "Execute the one action authorized by the admitted current TaskPlan step.",
            _object_schema({}),
        ))
        bindings.append(_ObjectiveActionBinding(option.action_id, context.execution_control.objective_parameters))
        grouped.clear()

    verb_counts: dict[str, int] = {}
    for (verb, _shape), values in grouped.items():
        verb_counts[verb] = verb_counts.get(verb, 0) + 1
        suffix = "" if verb_counts[verb] == 1 else f"_{verb_counts[verb]}"
        refs = [ref for ref, _option in values]
        schema, parameter_field = _verb_schema(verb, refs, values[0][1].parameter_schema)
        specs.append(ToolSpec(f"{verb}{suffix}", _tool_description(verb, refs, entity_by_ref), schema))
        bindings.append(_VerbBinding(tuple((ref, option.action_id) for ref, option in values), parameter_field))

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
    encoded = json.dumps(to_json_compatible(public), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded_bytes = len(encoded.encode())
    if len(specs) > MAX_GROUNDED_TOOL_COUNT or encoded_bytes > MAX_GROUNDED_WORKSPACE_BYTES:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    digest = hashlib.sha256(f"{context.context_id}\0{encoded}".encode()).hexdigest()[:32]
    return GroundedToolCatalog(
        f"grounded-catalog:{digest}", context.context_id, tuple(specs), tuple(bindings), view, encoded_bytes
    )


def resolve_grounded_tool_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> AgentDecision:
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
            expected_context_id, binding.query, binding.target_id, binding.relevance_role, binding.cursor
        )
        return decision
    if isinstance(binding, _ObserveBinding):
        return RequestObservation(
            expected_context_id,
            "current_world",
            binding.modality,
            binding.assurance,
            f"acquire fresh {binding.modality} grounding",
        )
    if isinstance(binding, _ObjectiveActionBinding):
        return SelectAction(expected_context_id, binding.action_id, dict(binding.parameters), "")
    if not isinstance(binding, _VerbBinding):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref = str(call.arguments.get("target") or "")
    actions = dict(binding.actions)
    if not ref and len(binding.actions) == 1:
        ref = binding.actions[0][0]
    if ref not in actions:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    parameters = {"value": call.arguments[binding.parameter_field]} if binding.parameter_field else {}
    return SelectAction(expected_context_id, actions[ref], parameters, "")


def _verb(semantic_action: str) -> str:
    return {"activate": "click", "fill": "fill", "select": "select"}.get(semantic_action, semantic_action)


def _shape_key(verb: str, schema: Mapping[str, object]) -> str:
    return verb + ":" + json.dumps(to_json_compatible(schema), sort_keys=True, separators=(",", ":"))


def _verb_schema(verb: str, refs: list[str], parameter_schema: Mapping[str, object]):
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
        raw_properties = parameter_schema.get("properties", {})
        if not isinstance(raw_properties, Mapping):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        properties["value"] = to_json_compatible(
            dict(raw_properties).get("value", {"type": "string"})
        )
        required.append("value")
        parameter_field = "value"
    elif parameter_schema.get("required"):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return _object_schema(properties, required), parameter_field


def _object_schema(properties: Mapping[str, object], required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _tool_description(verb: str, refs: list[str], entity_by_ref: Mapping[str, AgentGroundingEntityView]) -> str:
    values = [f"{ref}({entity_by_ref[ref].role},{entity_by_ref[ref].label!r})" for ref in refs]
    return f"{verb} one target authorized by the current Runtime action page. Targets: {'; '.join(values)}"[:500]


def _task_brief(context: AgentContext):
    return {
        "instruction": context.task.instruction,
        "constraints": list(context.task.constraints.items),
        "public_inputs": to_json_compatible(context.task.public_inputs),
    }


def _grounding_entity(item: AgentGroundingEntityView):
    return {
        "ref": item.ref,
        "role": item.role,
        "label": item.label,
        "state": to_json_compatible(item.state),
        "relations": list(item.relation_hints),
        "verbs": list(item.verbs),
        "marked": item.marked,
    }


def _current_state(context: AgentContext, ref_by_target: Mapping[str, str]):
    value = {
        "task_status": str(context.progress.validated_task_status),
        "verified_public_facts": [{
            "subject": ref_by_target.get(item.subject_id, "task"),
            "field": item.predicate,
            "value": to_json_compatible(item.value),
        } for item in context.progress.verified_public_facts],
        "remaining_turns": context.budgets.remaining_turns,
        "decision_mode": context.decision_mode.value,
    }
    if context.execution_control is not None:
        value["current_step_execution"] = {
            "disposition": context.execution_control.disposition,
            "reason": context.execution_control.reason_code,
            "candidate_count": context.execution_control.candidate_count,
            "matched_count": context.execution_control.matched_count,
            "certified": context.execution_control.certified,
            "predicate": to_json_compatible(context.execution_control.predicate),
            "evidence_needs": list(context.execution_control.evidence_needs),
        }
    return value


def _projected_execution_directive(context: AgentContext) -> ExecutionCatalogDirective:
    control = context.execution_control
    if control is None:
        raise ValueError("execution control projection is absent")
    return ExecutionCatalogDirective(
        ExecutionCatalogMode(control.mode),
        frozenset(control.allowed_action_ids),
        control.reason_code,
    )


def _previous_result(context: AgentContext, ref_by_target: Mapping[str, str]):
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
