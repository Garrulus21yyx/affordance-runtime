"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Mapping

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.actor_world_snapshot import countable_child_groups
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    CountChildren,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.immutable import to_json_compatible
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
from affordance_runtime.world.observation_needs import ObservationPurpose


@dataclass(frozen=True)
class _NextActionsBinding:
    query: str
    target_id: str
    relevance_role: str
    cursor: str


@dataclass(frozen=True)
class _EvidenceBinding:
    purposes: tuple[str, ...]
    subjects: Mapping[str, str]


@dataclass(frozen=True)
class _ControlBinding:
    kind: str


@dataclass(frozen=True)
class _CountChildrenBinding:
    container_refs: tuple[str, ...]


def compile_grounded_tool_catalog(
    context: AgentContext,
    phase: GroundedToolPhase,
) -> GroundedToolCatalog:
    if phase is not GroundedToolPhase.ACTION_SELECTION:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    specs: list[ToolSpec] = []
    bindings: list[object] = []
    if phase is GroundedToolPhase.ACTION_SELECTION:
        purposes: set[str] = set()
        for capability in context.world.observation_capabilities:
            if not _observation_tool_needed(context, capability):
                continue
            purposes.update(set(capability.purposes) & _AGENT_PURPOSES)
        if purposes:
            refs = context.grounding.private_subject_bindings()
            subjects = {"current_world": "current_world", **refs}
            ordered_purposes = tuple(sorted(purposes))
            specs.append(ToolSpec(
                "request_evidence",
                "Declare a semantic evidence gap. Runtime admits the need and chooses the provider, source, assurance, and acquisition mode.",
                _object_schema(
                    {
                        "purpose": {"type": "string", "enum": list(ordered_purposes)},
                        "subject": {"type": "string", "enum": list(subjects)},
                        "property": {
                            "type": "string",
                            "enum": ["color", "icon", "visual_state", "appearance"],
                        },
                    },
                    ("purpose", "subject"),
                ),
            ))
            bindings.append(_EvidenceBinding(ordered_purposes, subjects))

    if phase is GroundedToolPhase.ACTION_SELECTION:
        compiled = GroundedToolCompiler().compile(
            context.actions.options,
            context_id=context.context_id,
        )
        specs.extend(item.public_spec for item in compiled)
        bindings.extend(compiled)

    child_counts = countable_child_groups(context.actor_world)
    if child_counts:
        specs.append(ToolSpec(
            "count_children",
            "Required for counting repeated visible items: select every relevant current group; Runtime returns each exact direct-child count and their total.",
            _object_schema(
                {
                    "containers": {
                        "type": "array",
                        "description": "all relevant repeated-group references from the current observation",
                        "items": {"type": "string", "enum": list(child_counts)},
                        "minItems": 1,
                        "maxItems": len(child_counts),
                    }
                },
                ("containers",),
            ),
        ))
        bindings.append(_CountChildrenBinding(tuple(child_counts)))

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
    specs.extend(
        (
            ToolSpec(
                "ask_user",
                "Pause for task information unavailable from the interface. Never use this for action authorization or risk confirmation.",
                _object_schema(
                    {
                        "question": {"type": "string", "minLength": 1, "maxLength": 1000},
                        "requested_fields": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1, "maxLength": 120},
                            "maxItems": 8,
                        },
                    },
                    ("question",),
                ),
            ),
            ToolSpec(
                "wait",
                "Wait briefly for the current interface to settle, then observe again.",
                _object_schema(
                    {
                        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                        "max_wait_ms": {"type": "integer", "minimum": 1, "maximum": 60000},
                    },
                    ("reason", "max_wait_ms"),
                ),
            ),
            ToolSpec(
                "abort",
                "Stop when the task cannot continue safely or with current capabilities.",
                _object_schema(
                    {
                        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                        "category": {
                            "type": "string",
                            "enum": ["policy", "safety", "unsupported", "no_progress", "user_request"],
                        },
                    },
                    ("reason", "category"),
                ),
            ),
        )
    )
    bindings.extend(
        (
            _ControlBinding("ask_user"),
            _ControlBinding("wait"),
            _ControlBinding("abort"),
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
    return GroundedToolCatalog(
        catalog_id, context.context_id, tuple(specs), tuple(bindings), encoded_bytes
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
        return GroundedActionResolution(replace(decision, tool_call_id=call.call_id))
    if isinstance(binding, _EvidenceBinding):
        purpose = str(call.arguments["purpose"])
        subject_ref = str(call.arguments["subject"])
        evidence_property = str(call.arguments.get("property", ""))
        try:
            evidence_decision = RequestObservation(
                expected_context_id,
                purpose,
                binding.subjects[subject_ref],
                evidence_property,
                f"agent declared {purpose} evidence gap",
            )
        except (KeyError, ValueError) as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            ) from exc
        return GroundedActionResolution(replace(evidence_decision, tool_call_id=call.call_id))
    if isinstance(binding, _CountChildrenBinding):
        raw_refs = call.arguments["containers"]
        if not isinstance(raw_refs, list | tuple):
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            )
        container_refs = tuple(str(item) for item in raw_refs)
        if (
            len(set(container_refs)) != len(container_refs)
            or any(item not in binding.container_refs for item in container_refs)
        ):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        return GroundedActionResolution(
            CountChildren(expected_context_id, container_refs, call.call_id)
        )
    if isinstance(binding, _ControlBinding):
        control_decision: AgentDecision
        if binding.kind == "ask_user":
            requested_fields = call.arguments.get("requested_fields", ())
            if not isinstance(requested_fields, list | tuple):
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            control_decision = AskUser(
                expected_context_id,
                str(call.arguments["question"]),
                tuple(str(item) for item in requested_fields),
                call.call_id,
            )
        elif binding.kind == "wait":
            max_wait_ms = call.arguments["max_wait_ms"]
            if type(max_wait_ms) is not int:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            control_decision = Wait(
                expected_context_id,
                str(call.arguments["reason"]),
                max_wait_ms,
                call.call_id,
            )
        elif binding.kind == "abort":
            control_decision = Abort(
                expected_context_id,
                str(call.arguments["reason"]),
                str(call.arguments["category"]),
                call.call_id,
            )
        else:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        return GroundedActionResolution(control_decision)
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
    try:
        validate_value(parameters, match.parameter_schema, path="command")
    except ValueError as exc:
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.INVALID_ARGUMENTS
        ) from exc
    return GroundedActionResolution(
        SelectAction(
            expected_context_id,
            match.action_id,
            parameters,
            match.destination_id or "",
            call.call_id,
        ),
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


def _observation_tool_needed(context: AgentContext, capability) -> bool:
    current = tuple(
        source
        for source in context.world.sources
        if source.modality == capability.modality
        and source.freshness == "current"
    )
    return not current or any(
        source.projection_coverage != "complete"
        or source.conflict_status != "clear"
        for source in current
    )


_AGENT_PURPOSES = frozenset({
    ObservationPurpose.ENTITY_DISCOVERY.value,
    ObservationPurpose.TARGET_DISAMBIGUATION.value,
    ObservationPurpose.VISUAL_PROPERTY.value,
    ObservationPurpose.SPATIAL_RELATIONSHIP.value,
    ObservationPurpose.TEXT_IN_IMAGE.value,
    ObservationPurpose.CRITERION_VERIFICATION.value,
})
