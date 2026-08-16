"""One-way model-safe projection of a completed core step."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    CountChildren,
    FinalResponse,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.run_state import StepResult

_MAX_STRING = 240


def project_step_result(result: StepResult) -> AgentTurnView:
    """Pair one chosen action with its observed outcome and task status."""

    decision = result.decision
    if not isinstance(
        decision,
        (
            SelectAction,
            RequestObservation,
            RequestActionPage,
            AskUser,
            CountChildren,
            FinalResponse,
            ProposeDone,
            Wait,
            Abort,
        ),
    ):
        raise TypeError("policy failures do not enter model step history")
    if isinstance(decision, SelectAction) and result.execution is not None:
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
    target_id = ""
    if isinstance(decision, RequestObservation | RequestActionPage):
        target_id = decision.subject_id if isinstance(decision, RequestObservation) else decision.target_id
    summary = dict(project_decision_summary(decision))
    if result.tool_result is not None:
        summary["result"] = project_public_value(result.tool_result)
    summary["feedback_code"] = result.feedback
    return AgentTurnView(
        type(decision).__name__.lower(),
        _control_tool_name(decision),
        target_id,
        task_evaluation_status=str(result.task_evaluation.status),
        reason=result.feedback,
        semantic_summary=summary,
    )


def project_decision_summary(decision: AgentDecision) -> Mapping[str, object]:
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
        }
    if isinstance(decision, AskUser):
        return {"question": decision.question, "requested_fields": decision.requested_fields}
    if isinstance(decision, CountChildren):
        return {"containers": decision.container_refs}
    if isinstance(decision, FinalResponse):
        return {"content": _bounded(decision.content)}
    if isinstance(decision, ProposeDone):
        return {
            "claimed_criteria": decision.claimed_criteria,
            "result_summary": decision.result_summary,
            "unresolved_items": decision.unresolved_items,
        }
    if isinstance(decision, Wait):
        return {"reason": decision.reason, "max_wait_ms": decision.max_wait_ms}
    if isinstance(decision, Abort):
        return {"category": decision.category, "reason": decision.reason}
    return {}


def _control_tool_name(decision: AgentDecision) -> str:
    return {
        RequestObservation: "request_observation",
        RequestActionPage: "request_action_page",
        AskUser: "ask_user",
        CountChildren: "count_children",
        FinalResponse: "final_response",
        ProposeDone: "propose_done",
        Wait: "wait",
        Abort: "abort",
        SelectAction: "select_action",
    }[type(decision)]


def _bounded(value: str, limit: int = _MAX_STRING) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
