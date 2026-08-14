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
from affordance_runtime.model_policy.grounded_tool_compiler import (
    CompiledGroundedTool,
    GroundedToolCompiler,
)
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
    objective_open = context.progress.local_objective_open
    if phase is GroundedToolPhase.OBJECTIVE_PROPOSAL and objective_open:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
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


def _object_schema(properties: Mapping[str, object], required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _local_objective_schema() -> dict[str, object]:
    return TypeAdapter(LocalObjectiveSpecPayload).json_schema()


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
