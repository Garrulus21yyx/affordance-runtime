"""Single pure TaskEvaluation-to-loop-control disposition authority."""

from dataclasses import dataclass

from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.evaluation.contracts import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)


@dataclass(frozen=True)
class TaskEvaluationDisposition:
    status: AgentLoopStatus | None
    reason_code: str
    task_terminal: TaskOutcomeKind | None = None


def task_evaluation_disposition(evaluation: TaskEvaluation) -> TaskEvaluationDisposition:
    status = {
        TaskEvaluationStatus.COMPLETE: AgentLoopStatus.DONE,
        TaskEvaluationStatus.INCOMPLETE: None,
        TaskEvaluationStatus.UNKNOWN: AgentLoopStatus.WAITING_USER,
        TaskEvaluationStatus.BLOCKED: AgentLoopStatus.BLOCKED,
    }[evaluation.status]
    task_terminal = (
        TaskOutcomeKind.TERMINAL_FAILURE
        if evaluation.outcome is not None
        and evaluation.outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE
        else None
    )
    reason = "task_terminal_failure" if task_terminal is not None else f"task_{evaluation.status}"
    return TaskEvaluationDisposition(status, reason, task_terminal)


def task_evaluation_loop_status(evaluation: TaskEvaluation) -> AgentLoopStatus | None:
    """Compatibility view; production routing consumes the complete disposition."""

    return task_evaluation_disposition(evaluation).status
