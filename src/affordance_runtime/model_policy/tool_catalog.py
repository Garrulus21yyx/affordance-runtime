"""Pure compilation and resolution of current-page dynamic tools."""

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
from affordance_runtime.model_policy.tool_contracts import (
    MAX_TOOL_CATALOG_BYTES,
    ToolCall,
    ToolCatalog,
    ToolResolutionCode,
    ToolResolutionError,
    ToolSpec,
)
from affordance_runtime.task.frontier_contracts import NoObjectiveOperation
from affordance_runtime.world.schema_validation import validate_value

_DESTINATION_ARGUMENT = "destination_ref"


@dataclass(frozen=True)
class _ActionBinding:
    action_id: str
    parameter_schema: Mapping[str, object]
    destinations: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _NextActionPageBinding:
    query: str
    target_id: str
    relevance_role: str
    cursor: str


@dataclass(frozen=True)
class _NextObservationPageBinding:
    subject_id: str
    cursor: str


@dataclass(frozen=True)
class _RefreshObservationBinding:
    subjects: tuple[tuple[str, str], ...]
    capabilities: tuple[tuple[str, str, str], ...]


def compile_tool_catalog(serialized_context: str) -> ToolCatalog:
    try:
        context = json.loads(serialized_context)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID) from exc
    if not isinstance(context, dict):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    context_id = context.get("context_id")
    actions = context.get("actions")
    world = context.get("world")
    if not isinstance(context_id, str) or not isinstance(actions, dict) or not isinstance(world, dict):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)

    specs: list[ToolSpec] = []
    bindings: list[object] = []
    raw_options = actions.get("options", ())
    if not isinstance(raw_options, list):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    for index, option in enumerate(raw_options, 1):
        _append_action(specs, bindings, index, option)

    if actions.get("has_more") is True:
        cursor = actions.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
        specs.append(ToolSpec(
            "next_action_page",
            "Inspect the next in-memory page of currently legal actions.",
            _empty_schema(),
        ))
        bindings.append(_NextActionPageBinding(
            _string(actions.get("active_query")),
            _string(actions.get("active_target_filter")),
            _string(actions.get("active_relevance_filter")),
            cursor,
        ))

    traversal = world.get("traversal")
    targets = _world_targets(world)
    default_subject = targets[0][1] if targets else "world:current"
    if isinstance(traversal, dict) and traversal.get("status") == "partial":
        cursor = traversal.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
        specs.append(ToolSpec(
            "next_observation_page",
            "Inspect the next retained semantic page of this frozen observation.",
            _empty_schema(),
        ))
        bindings.append(_NextObservationPageBinding(default_subject, cursor))

    capabilities = _capabilities(world)
    if capabilities and targets:
        specs.append(ToolSpec(
            "refresh_observation",
            "Request a fresh backend observation for one visible subject and offered capability.",
            {
                "type": "object",
                "properties": {
                    "subject_ref": {"type": "string", "enum": [item[0] for item in targets]},
                    "capability_ref": {"type": "string", "enum": [item[0] for item in capabilities]},
                },
                "required": ["subject_ref", "capability_ref"],
                "additionalProperties": False,
            },
        ))
        bindings.append(_RefreshObservationBinding(tuple(targets), tuple(capabilities)))

    if not specs:
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    public = [{"name": item.name, "description": item.description, "input_schema": item.input_schema} for item in specs]
    encoded = json.dumps(to_json_compatible(public), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > MAX_TOOL_CATALOG_BYTES:
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    digest = hashlib.sha256(
        f"{context_id}\0{encoded}".encode()
    ).hexdigest()[:32]
    return ToolCatalog(
        f"tool-catalog:{digest}",
        context_id,
        tuple(specs),
        tuple(bindings),
        len(encoded.encode()),
    )


def resolve_tool_call(
    catalog: ToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> AgentDecisionPackage:
    if (
        catalog.context_id != expected_context_id
        or expected_catalog_id is not None
        and catalog.catalog_id != expected_catalog_id
    ):
        raise ToolResolutionError(ToolResolutionCode.STALE_CATALOG)
    try:
        index = next(index for index, spec in enumerate(catalog.specs) if spec.name == call.name)
    except StopIteration as exc:
        raise ToolResolutionError(ToolResolutionCode.UNKNOWN_TOOL) from exc
    spec = catalog.specs[index]
    binding = catalog.bindings[index]
    try:
        validate_value(call.arguments, spec.input_schema, path="tool_args")
    except ValueError as exc:
        raise ToolResolutionError(ToolResolutionCode.INVALID_ARGUMENTS) from exc

    if isinstance(binding, _ActionBinding):
        arguments = dict(call.arguments)
        destination_ref = arguments.pop(_DESTINATION_ARGUMENT, "")
        destinations = dict(binding.destinations)
        if destination_ref and destination_ref not in destinations:
            raise ToolResolutionError(ToolResolutionCode.UNKNOWN_DESTINATION)
        decision = SelectAction(
            expected_context_id,
            binding.action_id,
            arguments,
            destinations.get(str(destination_ref), ""),
        )
    elif isinstance(binding, _NextActionPageBinding):
        decision = RequestActionPage(
            expected_context_id,
            binding.query,
            binding.target_id,
            binding.relevance_role,
            binding.cursor,
        )
    elif isinstance(binding, _NextObservationPageBinding):
        decision = RequestObservation(
            expected_context_id,
            binding.subject_id,
            "structural",
            "structural",
            "continue retained observation traversal",
            binding.cursor,
        )
    else:
        assert isinstance(binding, _RefreshObservationBinding)
        subjects = dict(binding.subjects)
        capabilities = {ref: (modality, assurance) for ref, modality, assurance in binding.capabilities}
        subject_ref = str(call.arguments["subject_ref"])
        capability_ref = str(call.arguments["capability_ref"])
        if subject_ref not in subjects or capability_ref not in capabilities:
            raise ToolResolutionError(ToolResolutionCode.INVALID_ARGUMENTS)
        modality, assurance = capabilities[capability_ref]
        decision = RequestObservation(
            expected_context_id,
            subjects[subject_ref],
            modality,
            assurance,
            "request fresh observation for selected public subject",
        )
    return AgentDecisionPackage(NoObjectiveOperation(), decision)


def _append_action(specs: list[ToolSpec], bindings: list[object], index: int, raw: object) -> None:
    if not isinstance(raw, dict):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    action_id = raw.get("action_id")
    parameter_schema = raw.get("parameter_schema")
    if not isinstance(action_id, str) or not isinstance(parameter_schema, dict):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    properties = dict(parameter_schema.get("properties") or {})
    required = list(parameter_schema.get("required") or [])
    if _DESTINATION_ARGUMENT in properties:
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    destinations: list[tuple[str, str]] = []
    destination_section = raw.get("destinations")
    destination_items = destination_section.get("items", ()) if isinstance(destination_section, dict) else ()
    if not isinstance(destination_items, list):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    for destination_index, destination in enumerate(destination_items, 1):
        if not isinstance(destination, dict) or not isinstance(destination.get("destination_id"), str):
            raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
        ref = f"dest_{destination_index:02d}"
        destinations.append((ref, destination["destination_id"]))
    if raw.get("destination_required") is True:
        if not destinations:
            raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
        properties[_DESTINATION_ARGUMENT] = {
            "type": "string",
            "enum": [item[0] for item in destinations],
            "description": "Destination offered for this action.",
        }
        required.append(_DESTINATION_ARGUMENT)
    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    label = _string(raw.get("target_label")) or "visible target"
    if label.startswith(("entity:", "target:", "action:")):
        label = "visible target"
    semantic_action = _string(raw.get("semantic_action")) or "act"
    effects = raw.get("semantic_effects")
    effect_text = ", ".join(str(item) for item in effects[:4]) if isinstance(effects, list) else ""
    risk = _string(raw.get("risk")) or "unknown"
    public_description = f"{semantic_action} '{label}'. Risk: {risk}."
    if effect_text:
        public_description += f" Expected effects: {effect_text}."
    specs.append(ToolSpec(f"act_{index:02d}", public_description[:500], schema))
    bindings.append(_ActionBinding(action_id, parameter_schema, tuple(destinations)))


def _world_targets(world: Mapping[str, object]) -> list[tuple[str, str]]:
    section = world.get("targets")
    values = section.get("items", ()) if isinstance(section, dict) else ()
    if not isinstance(values, list):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    result = []
    for index, item in enumerate(values[:64], 1):
        if isinstance(item, dict) and isinstance(item.get("target_id"), str):
            result.append((f"subject_{index:02d}", item["target_id"]))
    return result


def _capabilities(world: Mapping[str, object]) -> list[tuple[str, str, str]]:
    values = world.get("observation_capabilities", ())
    if not isinstance(values, list):
        raise ToolResolutionError(ToolResolutionCode.CATALOG_INVALID)
    result = []
    for index, item in enumerate(values[:8], 1):
        if isinstance(item, dict) and isinstance(item.get("modality"), str) and isinstance(item.get("assurance"), str):
            result.append((f"capability_{index:02d}", item["modality"], item["assurance"]))
    return result


def _empty_schema() -> dict[str, object]:
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""
