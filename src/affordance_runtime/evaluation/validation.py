"""Deterministic validation of evaluator proposals against Runtime authority."""

from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_applicability import EvidenceApplicability, assess_criterion_evidence
from affordance_runtime.evaluation.output_validation import validate_required_outputs
from affordance_runtime.evaluation.success_expression import evaluate_success_expression
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.world.contracts import WorldObservation


def validate_action_outcome(
    evaluation: ActionOutcome,
    task: TaskGoal,
    request: BoundActionRequest,
    before: WorldObservation,
    after: WorldObservation,
    evidence_index: WorldEvidenceIndex,
) -> ActionOutcome:
    if (
        evaluation.request_id != request.request_id
        or evaluation.before_observation_id != before.observation_id
        or evaluation.after_observation_id != after.observation_id
    ):
        raise ValueError("action outcome lineage mismatch")
    if evidence_index.observation_id != after.observation_id:
        raise ValueError("action outcome evidence index is not current")
    unresolved = tuple(item for item in evaluation.evidence_refs if not evidence_index.resolve(item))
    if unresolved:
        raise ValueError("action outcome evidence does not resolve in the after observation")
    return apply_action_evidence_profile(evaluation, request, before, after, evidence_index)


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
    if evaluation.status == TaskEvaluationStatus.COMPLETE and expected != proposed:
        raise ValueError("COMPLETE task evaluation requires all expression criteria to be proposed")
    for criterion in evaluation.criteria:
        _require_resolved(criterion.evidence_refs, evidence_index, "criterion")
    normalized = {item.criterion_id: item for item in normalize_task_criteria(task)}
    for criterion in evaluation.criteria:
        spec = normalized[criterion.criterion_id]
        absent_semantic_scope = (
            criterion.status == CriterionEvaluationStatus.UNSATISFIED
            and not criterion.evidence_refs
            and spec.adjudicator == CriterionAdjudicator.SEMANTIC
            and _semantic_scope_absent_with_complete_coverage(spec, observation, evidence_index)
        )
        if criterion.status in {CriterionEvaluationStatus.SATISFIED, CriterionEvaluationStatus.UNSATISFIED} and not absent_semantic_scope and assess_criterion_evidence(
            spec, criterion, evidence_index
        ) != EvidenceApplicability.ACCEPTED:
            raise ValueError("task evaluation criterion evidence is not applicable")
    _require_resolved(evaluation.completion_evidence_refs, evidence_index, "completion evidence")
    if evaluation.outcome is not None:
        _require_resolved(evaluation.outcome.evidence_refs, evidence_index, "task outcome evidence")
    for output in evaluation.outputs:
        _require_resolved(output.evidence_refs, evidence_index, "output evidence")
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    expression = task.evaluation_spec.success_expression if task.evaluation_spec else None
    expression_result = evaluate_success_expression(expression, statuses) if expected and expected == proposed else None
    if evaluation.status == TaskEvaluationStatus.COMPLETE and expected and expression_result is not True:
        raise ValueError("COMPLETE task evaluation requires its Runtime success expression")
    if evaluation.status == TaskEvaluationStatus.COMPLETE:
        validate_required_outputs(task, evaluation, evidence_index)
    output_ids = {item.output_id for item in evaluation.outputs}
    outputs_pending = any(item not in output_ids for item in task.requested_outputs)
    if (
        evaluation.status == TaskEvaluationStatus.INCOMPLETE
        and expected and expression_result is True and not outputs_pending
    ):
        raise ValueError("INCOMPLETE task evaluation cannot satisfy its Runtime success expression")
    return evaluation


def _require_resolved(refs: tuple[str, ...], index: WorldEvidenceIndex, label: str) -> None:
    if any(not index.resolve(item) for item in refs):
        raise ValueError(f"task evaluation {label} does not resolve in the current observation")


def _semantic_scope_absent_with_complete_coverage(spec, observation, index) -> bool:
    complete = bool(observation.source_manifest) and all(
        str(item.coverage) == "complete" for item in observation.source_manifest
    )
    present = any(
        record.kind == "fact" and record.subject_id in spec.evidence_scope_target_ids
        or record.kind == "artifact" and record.output_id in spec.evidence_scope_output_ids
        for record in index.records
    )
    return complete and not present
