"""Canonical serialization of disposable model-facing AgentContext."""

from __future__ import annotations

import json
from dataclasses import replace

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.context import AgentContext


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
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized.encode()) > max_bytes:
        raise ValueError("AgentContext exceeds the configured serialized byte budget")
    return serialized
