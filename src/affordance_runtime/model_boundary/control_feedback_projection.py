"""One-way public projection of Runtime-owned control feedback."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.control_feedback import ControlFeedback


@dataclass(frozen=True)
class AgentControlFeedbackView:
    kind: str
    code: str
    source: str
    next_decision_disposition: str
    strategy_transition_required: bool
    public_subject_id: str | None
    public_field_paths: tuple[str, ...]


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
    )
