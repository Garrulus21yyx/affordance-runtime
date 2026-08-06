"""Pure recursive authority for TaskSpec completion semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    OutputMaterializationEvaluation,
    SuccessExpression,
    TaskCompletionEvaluation,
    criterion_policy_digest,
)

_INCONCLUSIVE_PRECEDENCE = (
    CriterionStatus.ERROR,
    CriterionStatus.CONFLICT,
    CriterionStatus.STALE,
    CriterionStatus.UNSUPPORTED,
    CriterionStatus.UNKNOWN,
)


@dataclass(frozen=True)
class TaskCompletionEvaluator:
    """Evaluate closure without mutating progress, state, trace, or terminal status."""

    @staticmethod
    def criterion_ids(task_spec: TaskSpec) -> frozenset[str]:
        """Return the finite criterion set admitted into task completion state."""

        success_ids = _expression_criterion_ids(task_spec.success)
        return frozenset(
            (
                *success_ids,
                *task_spec.constraint_criterion_ids,
                *task_spec.external_effect_criterion_ids,
                *task_spec.final_recheck_criterion_ids,
                *(output.materialization_criterion_id for output in task_spec.required_outputs),
            )
        )

    @staticmethod
    def success_criterion_ids(task_spec: TaskSpec) -> frozenset[str]:
        return _expression_criterion_ids(task_spec.success)

    def evaluate(
        self,
        *,
        task_spec: TaskSpec,
        criterion_results: tuple[CriterionEvaluation, ...],
        result_payload: Mapping[str, Any],
        output_source_bindings: Mapping[str, tuple[str, ...]] | None = None,
        uncertain_external_effects: tuple[str, ...] = (),
    ) -> TaskCompletionEvaluation:
        results = _result_index(criterion_results)
        high_risk_operation = task_spec.operation_class in {
            OperationClass.EXTERNAL_SIDE_EFFECT,
            OperationClass.IRREVERSIBLE,
        }
        declared_effects = task_spec.external_effect_criterion_ids
        declared_rechecks = task_spec.final_recheck_criterion_ids
        required_effect_gap = (
            ("task_spec:external_effect_evaluation_required",) if high_risk_operation and not declared_effects else ()
        )
        required_recheck_gap = (
            ("task_spec:authoritative_final_recheck_required",) if high_risk_operation and not declared_rechecks else ()
        )
        root_status = _evaluate_expression(task_spec.success, results)
        constraint_violations = tuple(
            criterion_id
            for criterion_id in task_spec.constraint_criterion_ids
            if _status_for(criterion_id, results) == CriterionStatus.UNSATISFIED
        )
        constraint_statuses = tuple(
            _status_for(criterion_id, results) for criterion_id in task_spec.constraint_criterion_ids
        )
        external_statuses = tuple(
            _status_for(criterion_id, results) for criterion_id in task_spec.external_effect_criterion_ids
        )
        unresolved_effects = tuple(
            dict.fromkeys(
                (
                    *uncertain_external_effects,
                    *required_effect_gap,
                    *(
                        criterion_id
                        for criterion_id in task_spec.external_effect_criterion_ids
                        if _status_for(criterion_id, results) != CriterionStatus.SATISFIED
                    ),
                )
            )
        )
        missing_rechecks = tuple(
            dict.fromkeys(
                (
                    *required_recheck_gap,
                    *(
                        criterion_id
                        for criterion_id in task_spec.final_recheck_criterion_ids
                        if not _authoritative_recheck_satisfied(criterion_id, results)
                    ),
                )
            )
        )
        output_results = _evaluate_outputs(
            task_spec,
            results,
            result_payload,
            output_source_bindings or {},
        )
        missing_outputs = tuple(item.output_id for item in output_results if item.status != CriterionStatus.SATISFIED)

        closure_statuses = (
            root_status,
            *constraint_statuses,
            *external_statuses,
            *(
                CriterionStatus.SATISFIED if criterion_id not in missing_rechecks else CriterionStatus.UNKNOWN
                for criterion_id in task_spec.final_recheck_criterion_ids
            ),
            *(item.status for item in output_results),
            *((CriterionStatus.UNKNOWN,) if unresolved_effects or missing_rechecks else ()),
        )
        status = _all_of_status(closure_statuses)
        return TaskCompletionEvaluation(
            status=status,
            root_criterion_id=task_spec.success.expression_id,
            criterion_results=criterion_results,
            required_output_results=output_results,
            missing_required_outputs=missing_outputs,
            missing_rechecks=missing_rechecks,
            constraint_violations=constraint_violations,
            uncertain_external_effects=unresolved_effects,
            result_payload=result_payload,
        )


def _result_index(
    criterion_results: tuple[CriterionEvaluation, ...],
) -> dict[str, CriterionEvaluation]:
    indexed: dict[str, CriterionEvaluation] = {}
    for result in criterion_results:
        if result.criterion_id in indexed:
            raise ValueError(f"duplicate criterion evaluation: {result.criterion_id}")
        indexed[result.criterion_id] = result
    return indexed


def _expression_criterion_ids(
    expression: SuccessExpression,
) -> frozenset[str]:
    if expression.operator == "criterion":
        return frozenset((expression.criterion_id,))
    return frozenset(criterion_id for child in expression.children for criterion_id in _expression_criterion_ids(child))


def _status_for(
    criterion_id: str,
    results: Mapping[str, CriterionEvaluation],
) -> CriterionStatus:
    result = results.get(criterion_id)
    return result.status if result is not None else CriterionStatus.UNKNOWN


def _evaluate_expression(
    expression: SuccessExpression,
    results: Mapping[str, CriterionEvaluation],
) -> CriterionStatus:
    if expression.operator == "criterion":
        result = results.get(expression.criterion_id)
        assert expression.policy is not None
        expected_policy = criterion_policy_digest(expression.criterion_id, expression.policy)
        if result is None or result.policy_digest != expected_policy:
            return CriterionStatus.UNKNOWN
        return result.status
    child_statuses = tuple(_evaluate_expression(child, results) for child in expression.children)
    if expression.operator == "all_of":
        return _all_of_status(child_statuses)
    if expression.operator == "any_of":
        if CriterionStatus.SATISFIED in child_statuses:
            return CriterionStatus.SATISFIED
        if child_statuses and all(item == CriterionStatus.UNSATISFIED for item in child_statuses):
            return CriterionStatus.UNSATISFIED
        return _inconclusive_status(child_statuses)
    child = child_statuses[0]
    if child == CriterionStatus.SATISFIED:
        return CriterionStatus.UNSATISFIED
    if child == CriterionStatus.UNSATISFIED:
        return CriterionStatus.SATISFIED
    return child


def _all_of_status(statuses: tuple[CriterionStatus, ...]) -> CriterionStatus:
    if not statuses or all(item == CriterionStatus.SATISFIED for item in statuses):
        return CriterionStatus.SATISFIED
    if CriterionStatus.UNSATISFIED in statuses:
        return CriterionStatus.UNSATISFIED
    return _inconclusive_status(statuses)


def _inconclusive_status(statuses: tuple[CriterionStatus, ...]) -> CriterionStatus:
    return next(
        (status for status in _INCONCLUSIVE_PRECEDENCE if status in statuses),
        CriterionStatus.UNKNOWN,
    )


def _authoritative_recheck_satisfied(
    criterion_id: str,
    results: Mapping[str, CriterionEvaluation],
) -> bool:
    result = results.get(criterion_id)
    return bool(
        result is not None and result.status == CriterionStatus.SATISFIED and result.authoritative_final_recheck
    )


def _evaluate_outputs(
    task_spec: TaskSpec,
    results: Mapping[str, CriterionEvaluation],
    result_payload: Mapping[str, Any],
    source_bindings: Mapping[str, tuple[str, ...]],
) -> tuple[OutputMaterializationEvaluation, ...]:
    evaluations: list[OutputMaterializationEvaluation] = []
    for output in task_spec.required_outputs:
        result_key = output.result_key or output.output_id
        criterion = results.get(output.materialization_criterion_id)
        criterion_status = criterion.status if criterion is not None else CriterionStatus.UNKNOWN
        materialized = result_key in result_payload and result_payload[result_key] is not None
        binding_refs = tuple(
            source_bindings.get(
                output.output_id,
                criterion.evidence_refs if criterion is not None else (),
            )
        )
        if not materialized:
            status = CriterionStatus.UNSATISFIED
            reason = "required_output_not_materialized"
        elif criterion_status != CriterionStatus.SATISFIED:
            status = criterion_status
            reason = "output_materialization_criterion_not_satisfied"
        elif output.source_binding_required and not binding_refs:
            status = CriterionStatus.UNSATISFIED
            reason = "required_output_not_source_bound"
        else:
            status = CriterionStatus.SATISFIED
            reason = "required_output_materialized"
        evaluations.append(
            OutputMaterializationEvaluation(
                output_id=output.output_id,
                status=status,
                materialization_criterion_id=output.materialization_criterion_id,
                evidence_refs=criterion.evidence_refs if criterion is not None else (),
                source_binding_refs=binding_refs,
                reason_code=reason,
            )
        )
    return tuple(evaluations)
