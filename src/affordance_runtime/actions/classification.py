"""Runtime-owned coarse effect and risk classification for surface bindings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.effect_authority import EffectClass, Externality, Reversibility
from affordance_runtime.actions.effect_policy import semantics_for_operation
from affordance_runtime.actions.space_contracts import ActionRisk
from affordance_runtime.task.contracts import RiskProfile, TaskGoal


class EffectCategory(StrEnum):
    OBSERVATION = "observation"
    INTERACTION = "interaction"
    LOCAL_REVERSIBLE = "local_reversible"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ActionClassification:
    category: EffectCategory
    semantic_effects: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool


def classify_dom_action(
    task: TaskGoal,
    affordance: object,
    semantic_action: str,
    *,
    trusted_interaction_operations: frozenset[str] = frozenset(),
) -> ActionClassification:
    role = str(getattr(affordance, "role", "")).casefold()
    externality = str(getattr(affordance, "externality", "")).casefold()
    reversibility = str(getattr(affordance, "reversibility", "")).casefold()
    operation_ref = str(getattr(affordance, "operation_ref", "")).casefold()
    classification = classify_surface_action(task, role, semantic_action)
    category = classification.category
    operation_semantics = semantics_for_operation(operation_ref)
    if operation_ref in trusted_interaction_operations and operation_semantics is not None and (
        operation_semantics.effect_class is EffectClass.INTERACTION_ONLY
        and operation_semantics.externality is Externality.LOCAL
        and operation_semantics.reversibility is Reversibility.REVERSIBLE
    ):
        category = EffectCategory.INTERACTION
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


def classify_surface_action(task: TaskGoal, role: str, semantic_action: str) -> ActionClassification:
    """Classify an action from semantic facts shared by every surface."""

    category = _base_category(semantic_action, role.casefold())
    return ActionClassification(
        category,
        _business_effects(task, "", category),
        _category_risk(category),
        category != EffectCategory.OBSERVATION,
    )


def classify_wot_action(
    task: TaskGoal,
    role: str,
    semantic_action: str,
    deployment_scope: object,
    *,
    authored_risk: str = "",
) -> ActionClassification:
    """Classify WoT actions from Runtime deployment scope, never TD trust."""

    if semantic_action == "read":
        category = EffectCategory.OBSERVATION
    elif str(deployment_scope) == "local_simulation":
        category = EffectCategory.LOCAL_REVERSIBLE
    else:
        category = EffectCategory.EXTERNAL
    risk = _category_risk(category)
    if authored_risk:
        try:
            risk = max((risk, ActionRisk(authored_risk)), key=_risk_rank)
        except ValueError:
            pass
    return ActionClassification(
        category,
        _business_effects(task, "", category),
        risk,
        category != EffectCategory.OBSERVATION,
    )


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
        EffectCategory.INTERACTION: ActionRisk.LOW,
        EffectCategory.LOCAL_REVERSIBLE: ActionRisk.LOW,
        EffectCategory.EXTERNAL: ActionRisk.HIGH,
        EffectCategory.IRREVERSIBLE: ActionRisk.IRREVERSIBLE,
    }[category]


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)
