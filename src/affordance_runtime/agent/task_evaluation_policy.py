"""Pure TaskEvaluation-to-loop-control policy."""

from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus


def task_evaluation_loop_status(evaluation: TaskEvaluation) -> AgentLoopStatus | None:
    return {
        TaskEvaluationStatus.COMPLETE: AgentLoopStatus.DONE,
        TaskEvaluationStatus.INCOMPLETE: None,
        TaskEvaluationStatus.UNKNOWN: AgentLoopStatus.WAITING_USER,
        TaskEvaluationStatus.BLOCKED: AgentLoopStatus.BLOCKED,
    }[evaluation.status]
