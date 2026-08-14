"""Disposable grounded action and LocalObjective proposal catalog.

Action tools are a one-way projection of current Runtime authority.  The sole
LocalObjective tool accepts a typed semantic proposal; it never reconstructs
authority from E-refs, action tools, or projected world data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from pydantic import TypeAdapter, ValidationError

from affordance_runtime.agent.decisions import (
    RequestActionPage,
    RequestObservation,
    SelectAction,
)
from affordance_runtime.agent.local_objective_proposal import (
    LocalObjectiveNeedsInput,
    LocalObjectiveNotRequired,
    LocalObjectiveProposal,
    LocalObjectiveResolvedOutcome,
    LocalObjectiveUnsupported,
    LocalObjectiveUnsupportedReason,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.contracts import AgentActionOptionView
from affordance_runtime.model_policy.grounded_tool_contracts import (
    MAX_GROUNDED_TOOL_COUNT,
    MAX_GROUNDED_WORKSPACE_BYTES,
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model_policy.objective_spec import (
    LocalObjectiveSpecPayload,
    local_objective_from_payload,
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
class _LocalObjectiveBinding:
    pass


@dataclass(frozen=True)
class _ObjectiveNotRequiredBinding:
    pass


@dataclass(frozen=True)
class _ObjectiveNeedsInputBinding:
    pass


@dataclass(frozen=True)
class _ObjectiveUnsupportedBinding:
    pass


def compile_grounded_tool_catalog(
    context: AgentContext,
    phase: GroundedToolPhase,
) -> GroundedToolCatalog:
    if context.actions.options and (not context.grounding.entities or not context.grounding.target_refs):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref_by_target = dict(context.grounding.target_refs)
    grouped: dict[tuple[str, str], list[tuple[str, AgentActionOptionView]]] = {}
    objective_open = context.progress.local_objective_open
    if phase is GroundedToolPhase.OBJECTIVE_PROPOSAL and objective_open:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    if phase is GroundedToolPhase.ACTION_SELECTION:
        for option in context.actions.options:
            ref = ref_by_target.get(option.target_id)
            if ref is None:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
            verb = _verb(option.semantic_action)
            grouped.setdefault((verb, _shape_key(verb, option.parameter_schema)), []).append((ref, option))

    specs: list[ToolSpec] = []
    bindings: list[object] = []
    if phase is GroundedToolPhase.OBJECTIVE_PROPOSAL:
        specs.extend(
            (
                ToolSpec(
                    "propose_local_objective",
                    "Propose one current/future observation-resolvable sequence, quantified set, or aggregate objective. "
                    "Use semantic predicates only. Runtime assigns objective/scope/step IDs; never put E-refs, DOM IDs, "
                    "screen points, private selectors, or bindings here.",
                    _object_schema({"value": _local_objective_schema()}, ("value",)),
                ),
                ToolSpec(
                    "local_objective_not_required",
                    "Declare that this task revision does not need a rolling LocalObjective before action selection.",
                    _object_schema({}),
                ),
                ToolSpec(
                    "local_objective_needs_input",
                    "Request bounded missing user input before a LocalObjective can be proposed.",
                    _object_schema(
                        {
                            "value": _object_schema(
                                {
                                    "question": {"type": "string", "minLength": 1, "maxLength": 1_000},
                                    "requested_fields": {
                                        "type": "array",
                                        "items": {"type": "string", "minLength": 1, "maxLength": 120},
                                        "maxItems": 32,
                                        "uniqueItems": True,
                                    },
                                },
                                ("question", "requested_fields"),
                            )
                        },
                        ("value",),
                    ),
                ),
                ToolSpec(
                    "local_objective_unsupported",
                    "Fail closed when no supported observation-resolvable objective can represent the task.",
                    _object_schema(
                        {
                            "value": _object_schema(
                                {
                                    "reason_code": {
                                        "type": "string",
                                        "enum": [item.value for item in LocalObjectiveUnsupportedReason],
                                    },
                                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                                },
                                ("reason_code", "reason"),
                            )
                        },
                        ("value",),
                    ),
                ),
            )
        )
        bindings.extend(
            (
                _LocalObjectiveBinding(),
                _ObjectiveNotRequiredBinding(),
                _ObjectiveNeedsInputBinding(),
                _ObjectiveUnsupportedBinding(),
            )
        )
    if phase is GroundedToolPhase.ACTION_SELECTION:
        seen_modalities: set[str] = set()
        for capability in context.world.observation_capabilities:
            if capability.modality in seen_modalities:
                continue
            seen_modalities.add(capability.modality)
            specs.append(
                ToolSpec(
                    f"observe_{capability.modality}",
                    _observation_tool_description(context, capability),
                    _object_schema({}),
                )
            )
            bindings.append(_ObserveBinding(capability.modality, capability.assurance))

    verb_counts: dict[str, int] = {}
    for (verb, _shape), values in grouped.items():
        verb_counts[verb] = verb_counts.get(verb, 0) + 1
        suffix = "" if verb_counts[verb] == 1 else f"_{verb_counts[verb]}"
        refs = [ref for ref, _option in values]
        schema, parameter_field = _verb_schema(verb, refs, values[0][1].parameter_schema)
        specs.append(ToolSpec(f"{verb}{suffix}", _tool_description(verb), schema))
        bindings.append(_VerbBinding(tuple((ref, option.action_id) for ref, option in values), parameter_field))

    if phase is GroundedToolPhase.ACTION_SELECTION and context.actions.has_more:
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
    digest = hashlib.sha256(f"{context.context_id}\0{encoded}".encode()).hexdigest()[:32]
    return GroundedToolCatalog(
        f"grounded-catalog:{digest}", context.context_id, tuple(specs), tuple(bindings), encoded_bytes
    )


def compile_grounded_action_catalog(context: AgentContext) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)


def compile_grounded_objective_catalog(context: AgentContext) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(context, GroundedToolPhase.OBJECTIVE_PROPOSAL)


def resolve_grounded_tool_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> GroundedActionResolution | LocalObjectiveResolvedOutcome:
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
    if isinstance(binding, _LocalObjectiveBinding):
        try:
            if set(call.arguments) != {"value"}:
                raise ValueError("local objective tool requires exactly one value")
            payload: LocalObjectiveSpecPayload = TypeAdapter(LocalObjectiveSpecPayload).validate_python(
                to_json_compatible(call.arguments["value"])
            )
            objective = local_objective_from_payload(payload)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
        return LocalObjectiveProposal(expected_context_id, objective)
    if isinstance(binding, _ObjectiveNotRequiredBinding):
        if call.arguments:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        return LocalObjectiveNotRequired(
            expected_context_id,
        )
    if isinstance(binding, _ObjectiveNeedsInputBinding):
        try:
            validate_value(call.arguments, spec.input_schema, path="command")
            value = call.arguments["value"]
            if not isinstance(value, Mapping):
                raise TypeError
            return LocalObjectiveNeedsInput(
                expected_context_id,
                str(value["question"]),
                tuple(value["requested_fields"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
    if isinstance(binding, _ObjectiveUnsupportedBinding):
        try:
            validate_value(call.arguments, spec.input_schema, path="command")
            value = call.arguments["value"]
            if not isinstance(value, Mapping):
                raise TypeError
            return LocalObjectiveUnsupported(
                expected_context_id,
                LocalObjectiveUnsupportedReason(str(value["reason_code"])),
                str(value["reason"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
    try:
        validate_value(call.arguments, spec.input_schema, path="command")
    except ValueError as exc:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS) from exc
    if isinstance(binding, _NextActionsBinding):
        decision = RequestActionPage(
            expected_context_id, binding.query, binding.target_id, binding.relevance_role, binding.cursor
        )
        return GroundedActionResolution(decision)
    if isinstance(binding, _ObserveBinding):
        return GroundedActionResolution(
            RequestObservation(
                expected_context_id,
                "current_world",
                binding.modality,
                binding.assurance,
                f"acquire fresh {binding.modality} grounding",
            ),
        )
    if not isinstance(binding, _VerbBinding):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    ref = str(call.arguments.get("target") or "")
    actions = dict(binding.actions)
    if ref not in actions:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    parameters = {"value": call.arguments[binding.parameter_field]} if binding.parameter_field else {}
    return GroundedActionResolution(
        SelectAction(expected_context_id, actions[ref], parameters, ""),
    )


def resolve_grounded_action_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> GroundedActionResolution:
    outcome = resolve_grounded_tool_call(
        catalog,
        call,
        expected_context_id=expected_context_id,
        expected_catalog_id=expected_catalog_id,
    )
    if not isinstance(outcome, GroundedActionResolution):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return outcome


def resolve_grounded_objective_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> LocalObjectiveResolvedOutcome:
    outcome = resolve_grounded_tool_call(
        catalog,
        call,
        expected_context_id=expected_context_id,
        expected_catalog_id=expected_catalog_id,
    )
    if isinstance(outcome, GroundedActionResolution):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return outcome


def _verb(semantic_action: str) -> str:
    return {"activate": "click", "fill": "fill", "select": "select"}.get(semantic_action, semantic_action)


def _shape_key(verb: str, schema: Mapping[str, object]) -> str:
    return verb + ":" + json.dumps(to_json_compatible(schema), sort_keys=True, separators=(",", ":"))


def _verb_schema(verb: str, refs: list[str], parameter_schema: Mapping[str, object]):
    properties: dict[str, object] = {
        "target": {"type": "string", "enum": refs},
    }
    required: list[str] = ["target"]
    parameter_field = ""
    if verb == "fill":
        properties["text"] = {"type": "string"}
        required.append("text")
        parameter_field = "text"
    elif verb == "select":
        raw_properties = parameter_schema.get("properties", {})
        if not isinstance(raw_properties, Mapping):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        properties["value"] = to_json_compatible(dict(raw_properties).get("value", {"type": "string"}))
        required.append("value")
        parameter_field = "value"
    elif parameter_schema.get("required"):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return _object_schema(properties, required), parameter_field


def _object_schema(properties: Mapping[str, object], required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _local_objective_schema() -> dict[str, object]:
    return TypeAdapter(LocalObjectiveSpecPayload).json_schema()


def _tool_description(verb: str) -> str:
    return (
        f"{verb} one entity authorized by the current Runtime action page. "
        "Pass exactly one required target E-ref from world.entities."
    )


def _observation_tool_description(context: AgentContext, capability) -> str:
    current = next(
        (
            source
            for source in context.world.sources
            if source.modality == capability.modality and source.freshness == "current"
        ),
        None,
    )
    if current is None:
        state = f"No current {capability.modality} source is present; acquire this evidence modality when needed."
    else:
        state = (
            f"A current {capability.modality} source is already present with "
            f"{current.projection_coverage} projection; refresh only when new currentness evidence is needed."
        )
    return f"{state} This tool takes no arguments; Runtime supplies the declared {capability.assurance} assurance."
