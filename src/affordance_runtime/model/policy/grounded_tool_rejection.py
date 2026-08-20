"""Shared ref-free rejection feedback after one parsed ActionPolicy ToolCall."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.decisions import LocalToolResult
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
    requested_ref = str(
        arguments.get("target")
        or arguments.get("exact_target")
        or arguments.get("source")
        or ""
    )
    return LocalToolResult(
        context_id,
        "tool_rejected",
        {
            "operation": operation,
            "arguments": to_json_compatible(arguments),
        },
        {
            "failure_kind": error.code.value,
            "attempted_operation": operation,
            "target": _target_semantics(agent_context, requested_ref),
            "failure_reason": error.detail or error.code.value,
            "available_operations": _available_operations(agent_context, requested_ref),
            "dispatch": "not_sent",
            "world_changed": False,
        },
        call.call_id,
    )


def _target_semantics(context: AgentContext, requested_ref: str) -> Mapping[str, object]:
    entity = next(
        (item for item in context.grounding.entities if item.ref == requested_ref),
        None,
    )
    return {} if entity is None else {"role": entity.role, "label": entity.label}


def _available_operations(context: AgentContext, requested_ref: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        item.operation
        for item in context.complete_actions
        if item.target_ref == requested_ref and item.operation
    ))[:16]
