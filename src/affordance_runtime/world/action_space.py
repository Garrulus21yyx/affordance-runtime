"""Deterministic construction and validation of offered semantic actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from affordance_runtime.world.contracts import ActionOption, ActionRisk, ActionSpace, WorldObservation

_FORBIDDEN_PARAMETER_KEYS = frozenset({"selector", "coordinate", "coordinates", "backend", "endpoint", "href"})


@dataclass(frozen=True)
class ActionSpaceBuilder:
    def build(self, observation: WorldObservation) -> ActionSpace:
        grouped: dict[tuple[str, str], list[Any]] = {}
        for binding in observation.bindings:
            for action in binding.supported_actions:
                grouped.setdefault((binding.target_id, action), []).append(binding)
        options = []
        for (target_id, action), bindings in sorted(grouped.items()):
            risk = max((binding.risk for binding in bindings), key=_risk_rank)
            schema = _semantic_parameter_schema(action)
            digest = hashlib.sha256(
                json.dumps([observation.observation_id, target_id, action], separators=(",", ":")).encode()
            ).hexdigest()[:16]
            options.append(
                ActionOption(
                    action_id=f"action:{digest}",
                    observation_id=observation.observation_id,
                    semantic_action=action,
                    target_id=target_id,
                    parameter_schema=schema,
                    description=f"{action} {target_id}",
                    risk=risk,
                )
            )
        return ActionSpace(observation.observation_id, tuple(options))

    def validate_parameters(self, option: ActionOption, parameters: dict[str, Any]) -> None:
        if _FORBIDDEN_PARAMETER_KEYS.intersection(parameters):
            raise ValueError("policy parameters contain runtime-private execution fields")
        schema = option.parameter_schema
        required = tuple(schema.get("required", ()))
        missing = [key for key in required if key not in parameters]
        if missing:
            raise ValueError(f"missing required semantic parameters: {', '.join(missing)}")
        allowed = set((schema.get("properties") or {}).keys())
        unknown = set(parameters) - allowed
        if unknown:
            raise ValueError(f"unknown semantic parameters: {', '.join(sorted(unknown))}")


def _semantic_parameter_schema(action: str) -> dict[str, Any]:
    if action in {"type", "fill"}:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    if action == "select":
        return {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)
