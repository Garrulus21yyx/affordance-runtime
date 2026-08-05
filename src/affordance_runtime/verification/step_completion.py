"""Pure typed evaluation of one active StepSpec completion contract."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.contracts import Observation
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.verification.contracts import CriterionEvaluation, CriterionStatus
from affordance_runtime.verification.mechanical import VerificationReport
from affordance_runtime.verification_report_adapter import admit_completion_evidence


@dataclass(frozen=True)
class StepCompletionEvaluator:
    def evaluate(
        self,
        step: StepSpec | None,
        report: VerificationReport | None,
        observation: Observation,
    ) -> CriterionEvaluation | None:
        if step is None:
            return None
        admitted = {
            item.criterion_id: item
            for item in admit_completion_evidence(
                observation=observation,
                report=report,
            )
        }
        leaves = tuple(admitted.get(item.criterion_id) for item in step.completion_criteria)
        missing = tuple(
            item.criterion_id
            for item, evaluation in zip(step.completion_criteria, leaves, strict=True)
            if evaluation is None
        )
        present = tuple(item for item in leaves if item is not None)
        statuses = {item.status for item in present}
        if missing:
            status = CriterionStatus.UNKNOWN
            reason = "step_criterion_evidence_missing"
        elif statuses == {CriterionStatus.SATISFIED}:
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
                    (item.criterion_id, item.status.value) for item in present
                ),
                "missing_criterion_ids": missing,
            },
            evidence_refs=tuple(
                dict.fromkeys(ref for item in present for ref in item.evidence_refs)
            ),
            evaluated_at_observation_ref=observation.snapshot_id,
            reason_code=reason,
        )
