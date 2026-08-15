"""Canonical serialization of disposable model-facing AgentContext."""

from __future__ import annotations

import json
from dataclasses import replace

from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.immutable import to_json_compatible


def serialize_agent_context(
    context: AgentContext,
    max_bytes: int = ContextProjectionBudget().max_total_serialized_bytes,
) -> str:
    # Binary perception is a transport side-channel. It must never be stringified
    # into the public AgentContext JSON or consume its semantic projection budget.
    payload = to_json_compatible(replace(context, image_inputs=()))
    if not isinstance(payload, dict):
        raise TypeError("AgentContext serialization requires an object")
    payload.pop("image_inputs", None)
    # Grounding aliases are an alternate protocol-specific allowlist projection.
    # Legacy structured-package serialization remains byte-for-byte independent
    # of that private resolver/index surface.
    payload.pop("grounding", None)
    # ActorWorldSnapshot belongs to the grounded flat-tool protocol. The legacy
    # structured-package protocol keeps its existing ModelWorldView contract.
    payload.pop("actor_world", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized.encode()) > max_bytes:
        raise ValueError("AgentContext exceeds the configured serialized byte budget")
    return serialized
