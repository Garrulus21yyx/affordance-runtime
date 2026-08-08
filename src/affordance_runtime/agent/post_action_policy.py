"""Effect-certainty decisions after fresh action observation."""

from affordance_runtime.agent.result import AgentResult, build_result
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
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
) -> AgentResult | None:
    task_status = task_evaluation_loop_status(task_evaluation)
    if task_status is not None:
        return build_result(task_status, task, state, 0, 0, task_evaluation.reason)
    if result.dispatch_status == DispatchStatus.SENT_UNKNOWN:
        state.set_pending_unknown_effect(request)
        return build_result(
            AgentLoopStatus.WAITING_USER,
            task,
            state,
            0,
            0,
            "effect remains unknown after transport uncertainty; request will not be replayed",
        )
    if action_evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        return None
    if action_evaluation.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED:
        return None
    if action_evaluation.status == ActionEvaluationStatus.REJECTED:
        return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, action_evaluation.reason)
    low_local = str(request.selection.risk) == "low" and request.selection.effect_category in {
        "observation", "local_reversible",
    }
    if result.dispatch_status == DispatchStatus.SENT and low_local:
        return None
    state.set_pending_unknown_effect(request)
    return build_result(
        AgentLoopStatus.WAITING_USER,
        task,
        state,
        0,
        0,
        "effect remains unknown after fresh observation; request will not be replayed",
    )
