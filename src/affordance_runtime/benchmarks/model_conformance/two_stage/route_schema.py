"""Dynamic provider schema for benchmark-only decision-kind routing."""

from __future__ import annotations

import json
from typing import Any

from affordance_runtime.model_policy.grounding import (
    build_compact_decision_guide_v2,
    serialize_compact_decision_guide_v2,
)
from affordance_runtime.model_policy.strict_json import strict_json_loads

from .contracts import DecisionKind, DecisionKindRoute


def route_candidate_kinds(serialized_context: str) -> tuple[DecisionKind, ...]:
    guide = json.loads(serialize_compact_decision_guide_v2(
        build_compact_decision_guide_v2(serialized_context),
    ))
    rows = guide["decision_contracts"]["items"]
    candidates = tuple(DecisionKind(row[0]) for row in rows if row[1] is True)
    if len(candidates) < 3:
        raise ValueError("routing diagnostics require at least three public candidates")
    return candidates


def build_route_schema(serialized_context: str) -> dict[str, object]:
    context_id = str(json.loads(serialized_context)["context_id"])
    candidates = route_candidate_kinds(serialized_context)
    return {
        "type": "object",
        "properties": {
            "context_id": {"type": "string", "const": context_id},
            "decision_type": {"type": "string", "enum": [item.value for item in candidates]},
        },
        "required": ["context_id", "decision_type"],
        "additionalProperties": False,
    }


def route_output_model(serialized_context: str) -> type[Any]:
    schema = build_route_schema(serialized_context)
    context_id = schema["properties"]["context_id"]["const"]  # type: ignore[index]
    candidates = frozenset(route_candidate_kinds(serialized_context))

    class BoundDecisionKindRoute:
        @classmethod
        def model_json_schema(cls) -> dict[str, object]:
            return schema

        @classmethod
        def model_validate_json(cls, raw: str | bytes | bytearray) -> DecisionKindRoute:
            value = strict_json_loads(raw.decode() if isinstance(raw, bytes | bytearray) else raw)
            if not isinstance(value, dict) or set(value) != {"context_id", "decision_type"}:
                raise ValueError("route output must contain exactly two fields")
            route = DecisionKindRoute(str(value["context_id"]), DecisionKind(value["decision_type"]))
            if route.context_id != context_id or route.decision_type not in candidates:
                raise ValueError("route output is outside the current public domain")
            return route

    BoundDecisionKindRoute.__name__ = "DecisionKindRoutePayload"
    return BoundDecisionKindRoute
