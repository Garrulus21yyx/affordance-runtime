"""Canonical serialization of disposable model-facing AgentContext."""

from __future__ import annotations

import json

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.context import AgentContext


def serialize_agent_context(
    context: AgentContext,
    max_bytes: int = ContextProjectionBudget().max_total_serialized_bytes,
) -> str:
    serialized = json.dumps(
        to_json_compatible(context),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized.encode()) > max_bytes:
        raise ValueError("AgentContext exceeds the configured serialized byte budget")
    return serialized
