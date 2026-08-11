"""Deterministic relevance over already legal and current action options."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.world.action_classification import EffectCategory
from affordance_runtime.world.contracts import ActionOption


class ActionObjective(Protocol):
    @property
    def direct_target_ids(self) -> tuple[str, ...]: ...

    @property
    def direct_effects(self) -> tuple[str, ...]: ...

    @property
    def enabling_target_ids(self) -> tuple[str, ...]: ...

    @property
    def enabling_action_hints(self) -> tuple[str, ...]: ...


class ActionRelevanceRole(StrEnum):
    DIRECT = "direct"
    ENABLING = "enabling"
    INFORMATION = "information"
    OTHER = "other"


@dataclass(frozen=True)
class ActionRelevance:
    role: ActionRelevanceRole
    score: float
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ActionRelevancePolicy:
    def classify(
        self,
        option: ActionOption,
        objective: ActionObjective | None,
    ) -> ActionRelevance:
        if objective is not None and (
            option.target_id in objective.direct_target_ids
            or bool(set(option.semantic_effects).intersection(objective.direct_effects))
        ):
            reasons = []
            if option.target_id in objective.direct_target_ids:
                reasons.append("explicit_direct_target")
            if set(option.semantic_effects).intersection(objective.direct_effects):
                reasons.append("explicit_direct_effect")
            return ActionRelevance(ActionRelevanceRole.DIRECT, 1.0, tuple(reasons))
        if objective is not None and (
            option.target_id in objective.enabling_target_ids
            or option.semantic_action in objective.enabling_action_hints
        ):
            reasons = []
            if option.target_id in objective.enabling_target_ids:
                reasons.append("explicit_enabling_target")
            if option.semantic_action in objective.enabling_action_hints:
                reasons.append("explicit_enabling_action")
            return ActionRelevance(ActionRelevanceRole.ENABLING, 0.75, tuple(reasons))
        if (
            option.semantic_action == "read"
            and option.effect_category == EffectCategory.OBSERVATION
            and not option.semantic_effects
        ):
            return ActionRelevance(ActionRelevanceRole.INFORMATION, 0.5, ("observation_action",))
        return ActionRelevance(ActionRelevanceRole.OTHER, 0.0, ("no_explicit_match",))
