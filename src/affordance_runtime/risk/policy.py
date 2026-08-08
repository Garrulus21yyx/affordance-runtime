"""Default Runtime-owned semantic risk policy."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.risk.contracts import RiskAssessment, RiskDecisionKind, semantic_subject_id
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.world.contracts import ActionRisk, AdmittedActionSelection


@dataclass(frozen=True)
class RiskPolicy:
    def assess(
        self,
        task: TaskGoal,
        selection: AdmittedActionSelection,
        *,
        destination_id: str = "",
    ) -> RiskAssessment:
        consequences = _consequences(selection)
        decision, reason = _decision(task, selection)
        return RiskAssessment(
            decision,
            selection.risk,
            tuple(sorted(selection.semantic_effects)),
            consequences,
            semantic_subject_id(
                selection,
                destination_id=destination_id,
                consequences=consequences,
            ),
            reason,
        )


def _decision(task: TaskGoal, selection: AdmittedActionSelection) -> tuple[RiskDecisionKind, str]:
    effects = set(selection.semantic_effects)
    if effects.intersection(task.forbidden_effects):
        return RiskDecisionKind.BLOCK, "semantic effect is explicitly forbidden by the task"
    if effects.difference(task.allowed_effects):
        return RiskDecisionKind.BLOCK, "semantic effect is outside the task's allowed effects"
    if task.risk_profile == RiskProfile.READ_ONLY and selection.semantic_action != "read":
        return RiskDecisionKind.BLOCK, "read-only task cannot execute effects"
    if selection.risk not in set(ActionRisk):
        return RiskDecisionKind.BLOCK, "unsupported action risk cannot be allowed"
    if task.risk_profile in {RiskProfile.MEDIUM, RiskProfile.HIGH}:
        return RiskDecisionKind.NEEDS_CONFIRMATION, "task risk requires semantic confirmation"
    if selection.risk in {ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE}:
        return RiskDecisionKind.NEEDS_CONFIRMATION, "action risk requires semantic confirmation"
    return RiskDecisionKind.ALLOW, "semantic action is allowed at the current risk level"


def _consequences(selection: AdmittedActionSelection) -> tuple[str, ...]:
    categories = {
        "observation": "observe current state",
        "local_reversible": "change local state",
        "external": "affect an external system",
        "irreversible": "cause an irreversible effect",
    }
    return (categories.get(selection.effect_category, "cause the declared semantic effects"),)
