"""Runtime-owned coarse effect and risk classification for surface bindings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.world.contracts import ActionRisk


class EffectCategory(StrEnum):
    OBSERVATION = "observation"
    LOCAL_REVERSIBLE = "local_reversible"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ActionClassification:
    category: EffectCategory
    semantic_effects: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool


def classify_dom_action(task: TaskGoal, affordance: object, semantic_action: str) -> ActionClassification:
    role = str(getattr(affordance, "role", "")).casefold()
    externality = str(getattr(affordance, "externality", "")).casefold()
    reversibility = str(getattr(affordance, "reversibility", "")).casefold()
    operation_ref = str(getattr(affordance, "operation_ref", "")).casefold()
    category = _base_category(semantic_action, role)
    if externality in {"external", "external_system", "remote"} or operation_ref.startswith("external."):
        category = EffectCategory.EXTERNAL
    if reversibility in {"irreversible", "none"}:
        category = EffectCategory.IRREVERSIBLE
    risk = _category_risk(category)
    authored_risk = getattr(getattr(affordance, "risk", None), "value", "")
    if bool(getattr(affordance, "risk_asserted", False)) and authored_risk:
        risk = max((risk, ActionRisk(authored_risk)), key=_risk_rank)
    effects = _business_effects(task, str(getattr(affordance, "effect_class", "")).strip(), category)
    return ActionClassification(category, effects, risk, category != EffectCategory.OBSERVATION)


def _base_category(semantic_action: str, role: str) -> EffectCategory:
    if semantic_action == "read":
        return EffectCategory.OBSERVATION
    if semantic_action == "activate" and role in {"button", "checkbox", "radio", "tab"}:
        return EffectCategory.LOCAL_REVERSIBLE
    return EffectCategory.EXTERNAL if role == "link" else EffectCategory.LOCAL_REVERSIBLE


def _business_effects(task: TaskGoal, hint: str, category: EffectCategory) -> tuple[str, ...]:
    if task.risk_profile == RiskProfile.READ_ONLY or category == EffectCategory.OBSERVATION:
        return ()
    if hint in task.forbidden_effects:
        return (hint,)
    if hint in task.allowed_effects:
        return (hint,)
    return tuple(task.allowed_effects) if len(task.allowed_effects) == 1 else ()


def _category_risk(category: EffectCategory) -> ActionRisk:
    return {
        EffectCategory.OBSERVATION: ActionRisk.LOW,
        EffectCategory.LOCAL_REVERSIBLE: ActionRisk.LOW,
        EffectCategory.EXTERNAL: ActionRisk.HIGH,
        EffectCategory.IRREVERSIBLE: ActionRisk.IRREVERSIBLE,
    }[category]


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)
