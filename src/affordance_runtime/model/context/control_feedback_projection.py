"""One-way public projection of Runtime-owned control feedback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.agent.control_feedback import ControlFeedback
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.context.projection import project_public_value


@dataclass(frozen=True)
class AgentRelatedDecisionView:
    kind: str
    action_id: str
    target_id: str
    destination_id: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class AgentContractViolationView:
    contract_owner: str
    code: str
    field_paths: tuple[str, ...]
    expected: Mapping[str, object]
    actual: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", freeze_json(self.expected))
        object.__setattr__(self, "actual", freeze_json(self.actual))


@dataclass(frozen=True)
class AgentSemanticEffectView:
    dispatch: str
    expected_effects: tuple[str, ...]
    observed_effect: str
    world_changed: bool
    action_space_changed: bool
    task_progress_changed: bool
    changed_public_fields: tuple[str, ...]


@dataclass(frozen=True)
class AgentRecoveryConstraintsView:
    must_change_fields: tuple[str, ...]
    repeat_previous_decision_allowed: bool
    retry_allowed: bool
    rollback_available: bool
    strategy_change_required: bool
    offered_action_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentControlFeedbackView:
    kind: str
    code: str
    source: str
    next_decision_disposition: str
    strategy_transition_required: bool
    public_subject_id: str | None
    public_field_paths: tuple[str, ...]
    related_decision: AgentRelatedDecisionView | None = None
    violation: AgentContractViolationView | None = None
    semantic_effect: AgentSemanticEffectView | None = None
    recovery: AgentRecoveryConstraintsView | None = None


def project_control_feedback(
    feedback: ControlFeedback | None,
) -> AgentControlFeedbackView | None:
    if feedback is None:
        return None
    if not isinstance(feedback, ControlFeedback):
        raise TypeError("model projection requires typed control feedback")
    return AgentControlFeedbackView(
        feedback.kind.value,
        feedback.code,
        feedback.source.value,
        feedback.next_decision_disposition.value,
        feedback.strategy_transition_required,
        feedback.public_subject_id,
        feedback.public_field_paths,
        AgentRelatedDecisionView(
            feedback.related_decision.kind,
            feedback.related_decision.action_id,
            feedback.related_decision.target_id,
            feedback.related_decision.destination_id,
            project_public_value(feedback.related_decision.parameters),
        ) if feedback.related_decision is not None else None,
        AgentContractViolationView(
            feedback.violation.contract_owner,
            feedback.violation.code,
            feedback.violation.field_paths,
            project_public_value(feedback.violation.expected),
            project_public_value(feedback.violation.actual),
        ) if feedback.violation is not None else None,
        AgentSemanticEffectView(
            feedback.semantic_effect.dispatch,
            feedback.semantic_effect.expected_effects,
            feedback.semantic_effect.observed_effect,
            feedback.semantic_effect.world_changed,
            feedback.semantic_effect.action_space_changed,
            feedback.semantic_effect.task_progress_changed,
            feedback.semantic_effect.changed_public_fields,
        ) if feedback.semantic_effect is not None else None,
        AgentRecoveryConstraintsView(
            feedback.recovery.must_change_fields,
            feedback.recovery.repeat_previous_decision_allowed,
            feedback.recovery.retry_allowed,
            feedback.recovery.rollback_available,
            feedback.recovery.strategy_change_required,
            feedback.recovery.offered_action_ids,
        ) if feedback.recovery is not None else None,
    )
