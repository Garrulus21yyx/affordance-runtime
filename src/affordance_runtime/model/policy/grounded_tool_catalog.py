"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Mapping

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.decisions import (
    RequestActionPage,
    RequestObservation,
    SelectAction,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.context.context import AgentContext
from affordance_runtime.model.policy.grounded_tool_compiler import (
    CompiledGroundedTool,
    GroundedToolCompiler,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    MAX_GROUNDED_TOOL_COUNT,
    MAX_GROUNDED_WORKSPACE_BYTES,
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec


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


def compile_grounded_tool_catalog(
    context: AgentContext,
    phase: GroundedToolPhase,
) -> GroundedToolCatalog:
    if phase is not GroundedToolPhase.ACTION_SELECTION:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    specs: list[ToolSpec] = []
    bindings: list[object] = []
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

    if phase is GroundedToolPhase.ACTION_SELECTION:
        compiled = GroundedToolCompiler().compile(
            context.actions.options,
            context_id=context.context_id,
        )
        specs.extend(item.public_spec for item in compiled)
        bindings.extend(compiled)

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
    catalog_id = f"grounded-catalog:{digest}"
    catalog_bindings = tuple(
        replace(
            binding,
            authority_equivalence_digest="sha256:" + hashlib.sha256(
                json.dumps(
                    (
                        catalog_id,
                        context.context_id,
                        binding.authority_equivalence_digest,
                    ),
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )
        if isinstance(binding, CompiledGroundedTool)
        else binding
        for binding in bindings
    )
    return GroundedToolCatalog(
        catalog_id, context.context_id, tuple(specs), catalog_bindings, encoded_bytes
    )


def compile_grounded_action_catalog(context: AgentContext) -> GroundedToolCatalog:
    return compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)


def resolve_grounded_tool_call(
    catalog: GroundedToolCatalog,
    call: ToolCall,
    *,
    expected_context_id: str,
    expected_catalog_id: str | None = None,
) -> GroundedActionResolution:
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
    if not isinstance(binding, CompiledGroundedTool):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    selector_names = tuple(item.public_name for item in binding.selector_fields)
    selector_values = {name: call.arguments[name] for name in selector_names}
    matches = tuple(
        item for item in binding.private_resolutions
        if dict(item.selector_values) == selector_values
    )
    if len(matches) != 1:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    match = matches[0]
    parameters = {
        name: value for name, value in call.arguments.items()
        if name not in selector_names
    }
    return GroundedActionResolution(
        SelectAction(expected_context_id, match.action_id, parameters, match.destination_id or ""),
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


def _object_schema(properties: Mapping[str, object], required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


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
