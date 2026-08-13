"""Single pure TaskEvaluation-to-loop-control disposition authority."""

from dataclasses import dataclass

from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.evaluation.contracts import (
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import ObservationCapabilities
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.source_profile import assurance_satisfies


@dataclass(frozen=True)
class TaskEvaluationDisposition:
    status: AgentLoopStatus | None
    reason_code: str
    task_terminal: TaskOutcomeKind | None = None


def task_evaluation_disposition(
    evaluation: TaskEvaluation,
    *,
    unknown_recoverable: bool = False,
) -> TaskEvaluationDisposition:
    status = {
        TaskEvaluationStatus.COMPLETE: AgentLoopStatus.DONE,
        TaskEvaluationStatus.INCOMPLETE: None,
        TaskEvaluationStatus.UNKNOWN: (
            None if unknown_recoverable else AgentLoopStatus.WAITING_USER
        ),
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


def task_evaluation_disposition_for_world(
    task: TaskGoal,
    evaluation: TaskEvaluation,
    observation: WorldObservation,
    capabilities: ObservationCapabilities,
) -> TaskEvaluationDisposition:
    """Allow policy control only when a missing typed source can resolve UNKNOWN."""

    return task_evaluation_disposition(
        evaluation,
        unknown_recoverable=_unknown_has_unacquired_authoritative_source(
            task,
            evaluation,
            observation,
            capabilities,
        ),
    )


def _unknown_has_unacquired_authoritative_source(
    task: TaskGoal,
    evaluation: TaskEvaluation,
    observation: WorldObservation,
    capabilities: ObservationCapabilities,
) -> bool:
    if evaluation.status is not TaskEvaluationStatus.UNKNOWN or not capabilities.independent_capture:
        return False
    unknown_ids = {
        item.criterion_id
        for item in evaluation.criteria
        if item.status is CriterionEvaluationStatus.UNKNOWN
    }
    if not unknown_ids:
        return False
    try:
        criteria = normalize_task_criteria(task)
    except ValueError:
        return False
    current_sources = {source.surface for source in observation.sources}
    for criterion in criteria:
        if (
            criterion.criterion_id not in unknown_ids
            or criterion.kind not in {"fact_equals", "target_state_equals"}
            or criterion.required_assurance != "authoritative"
        ):
            continue
        if any(
            offer.source not in current_sources
            and offer.modality == "environment_state"
            and assurance_satisfies(offer.assurance, criterion.required_assurance)
            for offer in capabilities.offers
        ):
            return True
    return False


def task_evaluation_loop_status(evaluation: TaskEvaluation) -> AgentLoopStatus | None:
    """Compatibility view; production routing consumes the complete disposition."""

    return task_evaluation_disposition(evaluation).status
