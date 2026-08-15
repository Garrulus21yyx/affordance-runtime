"""Default Runtime-owned semantic risk policy."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.actions.space_contracts import (
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.risk.contracts import ConfirmationSubject, RiskAssessment, RiskDecisionKind
from affordance_runtime.task.contracts import RiskProfile, TaskGoal


@dataclass(frozen=True)
class RiskPolicy:
    def assess(
        self,
        task: TaskGoal,
        selection: AdmittedActionSelection,
    ) -> RiskAssessment:
        consequences = _consequences(selection)
        effective_risk = _effective_risk(task.risk_profile, selection.risk)
        decision, reason = _decision(task, selection, effective_risk)
        subject = ConfirmationSubject.from_selection(
            selection,
            assessed_effects=tuple(sorted(selection.semantic_effects)),
            consequences=consequences,
            effective_risk=effective_risk,
        )
        return RiskAssessment(
            decision,
            effective_risk,
            tuple(sorted(selection.semantic_effects)),
            consequences,
            subject.subject_id,
            reason,
            subject,
        )


def _decision(
    task: TaskGoal,
    selection: AdmittedActionSelection,
    effective_risk: ActionRisk,
) -> tuple[RiskDecisionKind, str]:
    effects = set(selection.semantic_effects)
    if effects.intersection(task.forbidden_effects):
        return RiskDecisionKind.BLOCK, "semantic effect is explicitly forbidden by the task"
    if effects.difference(task.allowed_effects):
        return RiskDecisionKind.BLOCK, "semantic effect is outside the task's allowed effects"
    read_only_interaction = (
        selection.effect_category == "interaction"
        and selection.semantic_action == "activate"
        and not selection.semantic_effects
        and selection.risk is ActionRisk.LOW
    )
    if (
        task.risk_profile == RiskProfile.READ_ONLY
        and selection.semantic_action != "read"
        and not read_only_interaction
    ):
        return RiskDecisionKind.BLOCK, "read-only task cannot execute effects"
    if effective_risk in {ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE}:
        return RiskDecisionKind.NEEDS_CONFIRMATION, "action risk requires semantic confirmation"
    return RiskDecisionKind.ALLOW, "semantic action is allowed at the current risk level"


def _consequences(selection: AdmittedActionSelection) -> tuple[str, ...]:
    categories = {
        "observation": "observe current state",
        "interaction": "reveal or navigate local interface state",
        "local_reversible": "change local state",
        "external": "affect an external system",
        "irreversible": "cause an irreversible effect",
    }
    return (categories.get(selection.effect_category, "cause the declared semantic effects"),)


def _effective_risk(task_risk: RiskProfile, action_risk: ActionRisk) -> ActionRisk:
    floor = {
        RiskProfile.READ_ONLY: ActionRisk.LOW,
        RiskProfile.LOW: ActionRisk.LOW,
        RiskProfile.MEDIUM: ActionRisk.MEDIUM,
        RiskProfile.HIGH: ActionRisk.HIGH,
    }[task_risk]
    order = (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE)
    return max((floor, action_risk), key=order.index)
