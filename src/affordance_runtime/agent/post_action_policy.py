"""Effect-certainty decisions after fresh action observation."""

from affordance_runtime.agent.control_outcome import Continue, LoopDirective, directive
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_disposition
from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
)
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.task.contracts import TaskGoal


def post_action_result(
    task: TaskGoal,
    state: AgentLoopState,
    request: BoundActionRequest,
    result: ActionResult,
    action_evaluation: ActionEvaluation,
    task_evaluation: TaskEvaluation,
) -> LoopDirective:
    task_disposition = task_evaluation_disposition(task_evaluation)
    if task_disposition.status is not None:
        return directive(
            task_disposition.status,
            task_disposition.reason_code,
            task_evaluation.reason,
            task_terminal=task_disposition.task_terminal,
        )
    if result.dispatch_status == DispatchStatus.SENT_UNKNOWN:
        state.set_pending_unknown_effect(request)
        return directive(
            AgentLoopStatus.WAITING_USER,
            "effect_unknown",
            "effect remains unknown after transport uncertainty; request will not be replayed",
        )
    if action_evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        return Continue("action_effect_confirmed")
    if action_evaluation.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED:
        return Continue("action_no_effect_confirmed")
    if action_evaluation.status == ActionEvaluationStatus.REJECTED:
        return directive(AgentLoopStatus.FAILED, "action_rejected", action_evaluation.reason)
    low_local = str(request.selection.risk) == "low" and request.selection.effect_category in {
        "observation", "local_reversible",
    }
    if result.dispatch_status == DispatchStatus.SENT and low_local:
        return Continue("action_unknown_low_local")
    state.set_pending_unknown_effect(request)
    return directive(
        AgentLoopStatus.WAITING_USER,
        "effect_unknown",
        "effect remains unknown after fresh observation; request will not be replayed",
    )
