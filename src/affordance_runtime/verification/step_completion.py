"""Pure typed evaluation of one active StepSpec completion contract."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    PredicateEvidenceContext,
)
from affordance_runtime.verification.predicates import PredicateEvaluator


@dataclass(frozen=True)
class StepCompletionEvaluator:
    predicate_evaluator: PredicateEvaluator = PredicateEvaluator()

    def evaluate(
        self,
        step: StepSpec | None,
        context: PredicateEvidenceContext,
    ) -> CriterionEvaluation | None:
        if step is None:
            return None
        results = tuple(
            self.predicate_evaluator.evaluate(item, context)
            for item in step.completion_criteria
        )
        statuses = {item.status for item in results}
        if statuses == {CriterionStatus.SATISFIED}:
            status = CriterionStatus.SATISFIED
            reason = "all_step_criteria_satisfied"
        elif CriterionStatus.CONFLICT in statuses:
            status = CriterionStatus.CONFLICT
            reason = "step_criterion_conflict"
        elif CriterionStatus.ERROR in statuses:
            status = CriterionStatus.ERROR
            reason = "step_criterion_error"
        elif CriterionStatus.STALE in statuses:
            status = CriterionStatus.STALE
            reason = "step_criterion_stale"
        elif CriterionStatus.UNSUPPORTED in statuses:
            status = CriterionStatus.UNSUPPORTED
            reason = "step_criterion_unsupported"
        elif CriterionStatus.UNSATISFIED in statuses:
            status = CriterionStatus.UNSATISFIED
            reason = "step_criterion_unsatisfied"
        else:
            status = CriterionStatus.UNKNOWN
            reason = "step_criterion_unknown"
        return CriterionEvaluation(
            criterion_id=f"step:{step.step_id}:completion",
            status=status,
            observed_value={
                "criterion_statuses": tuple(
                    (item.criterion_id, item.status.value) for item in results
                ),
            },
            evidence_refs=tuple(
                dict.fromkeys(ref for item in results for ref in item.evidence_refs)
            ),
            evaluated_at_observation_ref=context.current_observation_ref,
            reason_code=reason,
        )
