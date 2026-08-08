"""Effect-certainty decisions after fresh action observation."""

from affordance_runtime.agent.result import AgentResult, build_result
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal


def post_action_result(
    task: TaskGoal,
    state: AgentLoopState,
    request: BoundActionRequest,
    action_evaluation: ActionEvaluation,
    task_evaluation: TaskEvaluation,
) -> AgentResult | None:
    if task_evaluation.status == TaskEvaluationStatus.COMPLETE:
        return build_result(AgentLoopStatus.DONE, task, state, 0, 0, task_evaluation.reason)
    if action_evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        return None
    if action_evaluation.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED:
        return None
    if action_evaluation.status == ActionEvaluationStatus.REJECTED:
        return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, action_evaluation.reason)
    state.pending_unknown_request = request
    return build_result(
        AgentLoopStatus.WAITING_USER,
        task,
        state,
        0,
        0,
        "effect remains unknown after fresh observation; request will not be replayed",
    )
