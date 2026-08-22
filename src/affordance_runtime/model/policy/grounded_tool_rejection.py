"""Shared ref-free rejection feedback after one parsed ActionPolicy ToolCall."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.agent.attempt_signature import public_attempt_signature
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.decisions import LocalToolResult, ToolRejectedResult
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolResolutionError
from affordance_runtime.model.policy.tool_contracts import ToolCall


def grounded_tool_rejection_decision(
    error: GroundedToolResolutionError,
    call: ToolCall,
    context_id: str,
    agent_context: AgentContext,
) -> LocalToolResult:
    """Preserve attempted semantics without carrying generation-local refs into history."""

    operation = call.name
    arguments = dict(call.arguments)
    requested_ref = str(arguments.get("target") or arguments.get("exact_target") or arguments.get("source") or "")
    target = _target_semantics(agent_context, requested_ref)
    supported = _available_operations(agent_context, requested_ref)
    mismatch = bool(target and supported and operation not in supported)
    target_id = _canonical_target_id(agent_context, requested_ref)
    destination_ref = str(arguments.get("destination") or "")
    signature = None
    if agent_context.current_observation is not None and target_id:
        signature = public_attempt_signature(
            operation,
            target_id,
            _canonical_target_id(agent_context, destination_ref),
            _semantic_parameters(arguments),
            agent_context.current_observation,
        )
    return ToolRejectedResult(
        context_id,
        "tool_rejected",
        {
            "operation": operation,
            "arguments": to_json_compatible(arguments),
        },
        {
            "kind": "operation_mismatch" if mismatch else error.code.value,
            "failure_kind": error.code.value,
            "attempted_operation": operation,
            "target": target,
            "failure_reason": error.detail or error.code.value,
            "supported_operations": supported,
            "must_change": ("operation",) if mismatch else (),
            "dispatch": "not_sent",
            "world_changed": False,
        },
        call.call_id,
        rejected_attempt_signature=signature,
    )


def _target_semantics(context: AgentContext, requested_ref: str) -> Mapping[str, object]:
    entity = next(
        (item for item in context.grounding.entities if item.ref == requested_ref),
        None,
    )
    return (
        {}
        if entity is None
        else {
            "role": entity.role,
            "label": entity.label,
            "context": entity.relation_hints[-4:],
        }
    )


def _available_operations(context: AgentContext, requested_ref: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.operation for item in context.complete_actions if item.target_ref == requested_ref and item.operation
        )
    )[:16]


def _canonical_target_id(context: AgentContext, requested_ref: str) -> str:
    return next(
        (target_id for target_id, ref in context.grounding.target_refs.items() if ref == requested_ref),
        "",
    )


def _semantic_parameters(arguments: Mapping[str, object]) -> Mapping[str, object]:
    return {
        key: value for key, value in arguments.items() if key not in {"target", "exact_target", "source", "destination"}
    }
