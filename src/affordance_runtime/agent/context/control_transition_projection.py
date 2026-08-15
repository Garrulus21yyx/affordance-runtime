"""One-way model-safe projection of canonical control transitions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.control_transition import ControlTransition
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)

if TYPE_CHECKING:
    from affordance_runtime.agent.run_state import StepResult

_MAX_STRING = 240


def project_control_transitions(
    transitions: tuple[ControlTransition, ...],
) -> tuple[AgentTurnView, ...]:
    return tuple(_project_transition(item) for item in transitions[-12:])


def project_select_action_step(result: StepResult) -> AgentTurnView:
    """Project one simplified-core action result without exposing its binding."""

    if not isinstance(result.decision, SelectAction) or result.execution is None:
        raise ValueError("select-action history requires one executed action")
    intent = result.execution.request.intent
    action = result.action_evaluation
    return AgentTurnView(
        "selectaction",
        intent.semantic_action,
        intent.target_id,
        intent.destination_id,
        project_public_value(intent.parameters),
        str(result.execution.result.dispatch_status),
        str(action.status) if action is not None else "",
        str(result.task_evaluation.status),
        action.reason if action is not None else result.feedback,
        {"feedback_code": result.feedback},
    )


def _project_transition(transition: ControlTransition) -> AgentTurnView:
    action = transition.action_evaluation
    if action is not None and action.after_observation_id != transition.after_observation_id:
        action = None
    task = transition.task_evaluation
    if task is not None and task.observation_id != transition.after_observation_id:
        task = None
    intent = transition.intent
    summary = dict(project_decision_summary(transition.decision, transition.decision_result))
    summary.update({
        "resulting_status": str(transition.resulting_status or ""),
        "reason_code": transition.reason_code,
        "pending_kind": str(transition.pending_kind),
        "execution_attempt_count": len(transition.execution_attempts),
        "acquisition_attempt_count": len(transition.acquisition_attempts),
    })
    return AgentTurnView(
        type(transition.decision).__name__.lower(),
        intent.semantic_action if intent else "",
        intent.target_id if intent else "",
        intent.destination_id if intent else "",
        project_public_value(intent.parameters) if intent else {},
        transition.execution.result.dispatch_status if transition.execution else "",
        action.status if action else "",
        task.status if task else "",
        transition.reason_code,
        summary,
    )


def project_decision_summary(
    decision: AgentDecision,
    decision_result: str = "",
) -> Mapping[str, object]:
    """Deterministically project non-action decision details for model views."""

    if isinstance(decision, RequestObservation):
        return {
            "subject_id": _bounded(decision.subject_id),
            "purpose": decision.purpose,
            "evidence_property": decision.evidence_property,
            "reason": _bounded(decision.reason),
        }
    if isinstance(decision, RequestActionPage):
        return {
            "query": _bounded(decision.query, 120),
            "target_id": _bounded(decision.target_id),
            "relevance_role": decision.relevance_role,
            "cursor_requested": bool(decision.cursor),
            "result": decision_result,
        }
    if isinstance(decision, AskUser):
        return {"question": decision.question, "requested_fields": decision.requested_fields}
    if isinstance(decision, ProposeDone):
        return {
            "claimed_criteria": decision.claimed_criteria,
            "result_summary": decision.result_summary,
            "unresolved_items": decision.unresolved_items,
        }
    if isinstance(decision, Wait):
        return {
            "reason": decision.reason,
            "max_wait_ms": decision.max_wait_ms,
            "result": decision_result,
        }
    if isinstance(decision, Abort):
        return {"category": decision.category, "reason": decision.reason}
    return {}


def _bounded(value: str, limit: int = _MAX_STRING) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
