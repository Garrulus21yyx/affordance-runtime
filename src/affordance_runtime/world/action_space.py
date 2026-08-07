"""Task-aware construction and validation of offered semantic actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import time
from typing import Any

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.task.planning_contracts import LocalObjective
from affordance_runtime.world.contracts import ActionBinding, ActionOption, ActionRisk, ActionSpace, WorldObservation
from affordance_runtime.world.schema_validation import validate_value

_FORBIDDEN_PARAMETER_KEYS = frozenset({"selector", "coordinate", "coordinates", "backend", "endpoint", "href"})


@dataclass(frozen=True)
class ActionSpaceBuilder:
    def build(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        objective: LocalObjective | None = None,
    ) -> ActionSpace:
        del objective  # Reserved for desired-state narrowing; it never grants effects.
        conflicted_targets = {conflict.subject_id for conflict in observation.conflicts}
        grouped: dict[tuple[str, str, tuple[str, ...], str], list[ActionBinding]] = {}
        for binding in observation.bindings:
            if binding.target_id in conflicted_targets:
                continue
            if not _binding_is_current(binding, observation) or not _effects_allowed(task, binding):
                continue
            schema_key = json.dumps(to_json_compatible(binding.parameter_schema), sort_keys=True, separators=(",", ":"))
            key = (binding.target_id, binding.semantic_action, binding.semantic_effects, schema_key)
            grouped.setdefault(key, []).append(binding)
        options = []
        for (target_id, action, effects, _), bindings in sorted(grouped.items()):
            risk = max((binding.risk for binding in bindings), key=_risk_rank)
            digest = hashlib.sha256(
                json.dumps([observation.observation_id, target_id, action, effects], separators=(",", ":")).encode()
            ).hexdigest()[:16]
            options.append(
                ActionOption(
                    action_id=f"action:{digest}",
                    observation_id=observation.observation_id,
                    semantic_action=action,
                    target_id=target_id,
                    parameter_schema=to_json_compatible(bindings[0].parameter_schema),
                    description=f"{action} {target_id}",
                    semantic_effects=effects,
                    risk=risk,
                    observation_barrier=any(binding.observation_barrier for binding in bindings),
                )
            )
        return ActionSpace(observation.observation_id, tuple(options))

    def validate_parameters(self, option: ActionOption, parameters: dict[str, Any]) -> None:
        if _FORBIDDEN_PARAMETER_KEYS.intersection(parameters):
            raise ValueError("policy parameters contain runtime-private execution fields")
        validate_value(parameters, option.parameter_schema)


def _binding_is_current(binding: ActionBinding, observation: WorldObservation) -> bool:
    if binding.world_observation_id != observation.observation_id:
        return False
    if not binding.target_fingerprint or (binding.expires_at_s and time() > binding.expires_at_s):
        return False
    if not observation.sources:
        return binding.source_observation_id == observation.observation_id
    source = next((item for item in observation.sources if item.surface == binding.surface), None)
    return bool(
        source
        and binding.source_observation_id == source.observation_id
        and binding.source_revision == source.revision
    )


def _effects_allowed(task: TaskGoal, binding: ActionBinding) -> bool:
    effects = set(binding.semantic_effects)
    if effects.intersection(task.forbidden_effects):
        return False
    if task.risk_profile == RiskProfile.READ_ONLY:
        return binding.semantic_action == "read" and not effects
    return bool(effects) and effects.issubset(task.allowed_effects)


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)
