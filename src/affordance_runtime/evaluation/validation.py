"""Deterministic validation of evaluator proposals against Runtime authority."""

from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.output_validation import validate_required_outputs
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.world.contracts import WorldObservation


def validate_action_evaluation(
    evaluation: ActionEvaluation,
    request: BoundActionRequest,
    before: WorldObservation,
    after: WorldObservation,
    evidence_index: WorldEvidenceIndex,
) -> None:
    if (
        evaluation.request_id != request.request_id
        or evaluation.before_observation_id != before.observation_id
        or evaluation.after_observation_id != after.observation_id
    ):
        raise ValueError("action evaluation lineage mismatch")
    if evidence_index.observation_id != after.observation_id:
        raise ValueError("action evaluation evidence index is not current")
    unresolved = tuple(item for item in evaluation.evidence_refs if not evidence_index.resolve(item))
    if unresolved:
        raise ValueError("action evaluation evidence does not resolve in the after observation")


def validate_task_evaluation(
    evaluation: TaskEvaluation,
    task: TaskGoal,
    observation: WorldObservation,
    evidence_index: WorldEvidenceIndex,
) -> TaskEvaluation:
    if evaluation.task_id != task.task_id:
        raise ValueError("task evaluation task identity mismatch")
    if evaluation.observation_id != observation.observation_id:
        raise ValueError("task evaluation observation identity mismatch")
    if evidence_index.observation_id != observation.observation_id:
        raise ValueError("task evaluation evidence index is not current")
    expected = {criterion_id(item) for item in task.success_criteria}
    proposed = {item.criterion_id for item in evaluation.criteria}
    if not proposed.issubset(expected):
        raise ValueError("task evaluation contains an unknown criterion")
    for criterion in evaluation.criteria:
        _require_resolved(criterion.evidence_refs, evidence_index, "criterion")
    _require_resolved(evaluation.completion_evidence_refs, evidence_index, "completion evidence")
    for output in evaluation.outputs:
        _require_resolved(output.evidence_refs, evidence_index, "output evidence")
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    all_satisfied = bool(expected) and expected == proposed and all(
        statuses[item] == CriterionEvaluationStatus.SATISFIED for item in expected
    )
    if evaluation.status == TaskEvaluationStatus.COMPLETE and expected and not all_satisfied:
        raise ValueError("COMPLETE task evaluation requires all success criteria satisfied")
    if evaluation.status == TaskEvaluationStatus.COMPLETE:
        validate_required_outputs(task, evaluation, evidence_index)
    if evaluation.status == TaskEvaluationStatus.INCOMPLETE and all_satisfied:
        raise ValueError("INCOMPLETE task evaluation cannot claim all criteria satisfied")
    return evaluation


def _require_resolved(refs: tuple[str, ...], index: WorldEvidenceIndex, label: str) -> None:
    if any(not index.resolve(item) for item in refs):
        raise ValueError(f"task evaluation {label} does not resolve in the current observation")
