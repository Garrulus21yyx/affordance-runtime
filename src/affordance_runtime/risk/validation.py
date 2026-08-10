"""Fail-closed validation for the public, replaceable risk-policy boundary."""

from __future__ import annotations

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.world.contracts import ActionRisk, AdmittedActionSelection


def validate_risk_assessment(
    task: TaskGoal,
    selection: AdmittedActionSelection,
    value: object,
) -> RiskAssessment:
    if not isinstance(value, RiskAssessment):
        raise TypeError("risk policy returned a malformed assessment")
    subject = value.subject
    if (
        subject.semantic_action != selection.semantic_action
        or subject.target_id != selection.target_id
        or subject.destination_id != selection.destination_id
        or to_json_compatible(subject.parameters)
        != to_json_compatible(selection.parameters)
        or subject.selection_effects != tuple(sorted(selection.semantic_effects))
        or subject.effect_category != selection.effect_category
        or not set(selection.semantic_effects).issubset(subject.assessed_effects)
        or _risk_rank(subject.risk) < _risk_rank(selection.risk)
        or _risk_rank(subject.risk) < _risk_rank(_task_risk_floor(task.risk_profile))
    ):
        raise ValueError("risk assessment does not describe the current selection")
    return value


def _task_risk_floor(value: RiskProfile) -> ActionRisk:
    return {
        RiskProfile.READ_ONLY: ActionRisk.LOW,
        RiskProfile.LOW: ActionRisk.LOW,
        RiskProfile.MEDIUM: ActionRisk.MEDIUM,
        RiskProfile.HIGH: ActionRisk.HIGH,
    }[value]


def _risk_rank(value: ActionRisk) -> int:
    return (
        ActionRisk.LOW,
        ActionRisk.MEDIUM,
        ActionRisk.HIGH,
        ActionRisk.IRREVERSIBLE,
    ).index(value)
