"""Disposable grounded action catalog projected from current Runtime authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView, ActorWorldSnapshot
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    Wait,
)
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


@dataclass(frozen=True)
class _NextActionsBinding:
    query: str
    target_id: str
    relevance_role: str
    cursor: str

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        del arguments
        return RequestActionPage(
            context_id,
            self.query,
            self.target_id,
            self.relevance_role,
            self.cursor,
            tool_call_id,
        )


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
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            ) from exc


@dataclass(frozen=True)
class _ControlBinding:
    kind: str

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        if self.kind == "ask_user":
            requested_fields = arguments.get("requested_fields", ())
            if not isinstance(requested_fields, list | tuple):
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.INVALID_ARGUMENTS
                )
            return AskUser(
                context_id,
                str(arguments["question"]),
                tuple(str(item) for item in requested_fields),
                tool_call_id,
            )
        if self.kind == "wait":
            max_wait_ms = arguments["max_wait_ms"]
            if type(max_wait_ms) is not int:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.INVALID_ARGUMENTS
                )
            return Wait(
                context_id,
                str(arguments["reason"]),
                max_wait_ms,
                tool_call_id,
            )
        if self.kind == "abort":
            return Abort(
                context_id,
                str(arguments["reason"]),
                str(arguments["category"]),
                tool_call_id,
            )
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)


@dataclass(frozen=True)
class _CountChildrenBinding:
    counts: Mapping[str, int]

    def resolve(self, arguments, context_id: str, tool_call_id: str) -> AgentDecision:
        raw_refs = arguments["containers"]
        if not isinstance(raw_refs, list | tuple):
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            )
        container_refs = tuple(str(item) for item in raw_refs)
        if (
            len(set(container_refs)) != len(container_refs)
            or any(item not in self.counts for item in container_refs)
        ):
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            )
        counts = {item: self.counts[item] for item in container_refs}
        return LocalToolResult(
            context_id,
            "count_children",
            {"containers": container_refs},
            {"counts": counts, "total": sum(counts.values())},
            tool_call_id,
        )


def compile_grounded_tool_catalog(
    context: AgentContext,
    phase: GroundedToolPhase,
) -> GroundedToolCatalog:
    if phase is not GroundedToolPhase.ACTION_SELECTION:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    registered: list[RegisteredGroundedTool] = []

    purposes: set[str] = set()
    for capability in context.actor_world.observation_capabilities:
        if _observation_tool_needed(context, capability):
            purposes.update(set(capability["purposes"]) & _AGENT_PURPOSES)
    if purposes:
        refs = context.grounding.private_subject_bindings()
        subjects = {"current_world": "current_world", **refs}
        ordered_purposes = tuple(sorted(purposes))
        registered.append(RegisteredGroundedTool(
            ToolSpec(
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
            ),
            _EvidenceBinding(ordered_purposes, subjects),
        ))

    registered.extend(
        RegisteredGroundedTool(item.public_spec, item)
        for item in GroundedToolCompiler().compile(
            context.actions.options,
            context_id=context.context_id,
        )
    )

    child_counts = _countable_child_groups(context.actor_world)
    if child_counts:
        registered.append(RegisteredGroundedTool(
            ToolSpec(
                "count_children",
                "Mechanically count direct children of selected complete repeated groups and return each count plus the total.",
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
            ),
            _CountChildrenBinding(child_counts),
        ))

    if context.actions.has_more:
        registered.append(RegisteredGroundedTool(
            ToolSpec(
                "next_actions",
                "Inspect the next in-memory page of currently legal actions.",
                _object_schema({}),
            ),
            _NextActionsBinding(
                context.actions.active_query,
                context.actions.active_target_filter,
                context.actions.active_relevance_filter,
                context.actions.next_cursor,
            ),
        ))

    registered.extend((
        RegisteredGroundedTool(
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
            _ControlBinding("ask_user"),
        ),
        RegisteredGroundedTool(
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
            _ControlBinding("wait"),
        ),
        RegisteredGroundedTool(
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
            _ControlBinding("abort"),
        ),
    ))
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
    digest = hashlib.sha256(f"{context.context_id}\0{encoded}".encode()).hexdigest()[:32]
    catalog_id = f"grounded-catalog:{digest}"
    return GroundedToolCatalog(
        catalog_id, context.context_id, tuple(registered), encoded_bytes
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
    resolver = getattr(binding, "resolve", None)
    if not callable(resolver):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    try:
        decision = resolver(call.arguments, expected_context_id, call.call_id)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, GroundedToolResolutionError):
            raise
        raise GroundedToolResolutionError(
            GroundedToolResolutionCode.INVALID_ARGUMENTS
        ) from exc
    return GroundedActionResolution(decision)


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
        for source in context.actor_world.sources
        if source.modality == capability["modality"]
        and source.freshness == "current"
    )
    return not current or any(
        source.projection_coverage != "complete"
        or bool(context.actor_world.conflicts)
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
    return all(
        (child.role, child.label, child.state, len(child.children)) == shape
        for child in children[1:]
    )
