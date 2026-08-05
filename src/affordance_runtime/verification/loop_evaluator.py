"""Loop-native composition of distinct action, step, and task evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.contracts import ExecutionReceipt, Observation
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    LoopEvaluation,
    TaskCompletionEvaluation,
)
from affordance_runtime.verification.mechanical import VerificationReport
from affordance_runtime.verification.step_completion import StepCompletionEvaluator


@dataclass(frozen=True)
class LoopEvaluator:
    step_evaluator: StepCompletionEvaluator = field(default_factory=StepCompletionEvaluator)

    def evaluate(
        self,
        *,
        receipt: ExecutionReceipt,
        report: VerificationReport,
        observation: Observation,
        active_step: StepSpec | None,
        task_completion: TaskCompletionEvaluation | None,
    ) -> LoopEvaluation:
        independent = tuple(
            item
            for item in report.evidence
            if item.source not in {"receipt", "execution_receipt"}
            and item.strength in {"strong", "authoritative"}
        )
        if independent:
            passed = {item.passed for item in independent}
            action_status = (
                CriterionStatus.CONFLICT
                if len(passed) > 1
                else CriterionStatus.SATISFIED
                if True in passed
                else CriterionStatus.UNSATISFIED
            )
            reason = "independent_action_effect_evidence"
        else:
            action_status = CriterionStatus.UNKNOWN
            reason = (
                "receipt_success_is_not_effect_evidence"
                if receipt.success
                else "dispatch_failed_without_effect_evidence"
            )
        action_effect = CriterionEvaluation(
            criterion_id=f"contract:{receipt.contract_id}:effect",
            status=action_status,
            evidence_refs=tuple(item.evidence_id for item in independent if item.evidence_id),
            evaluated_at_observation_ref=observation.snapshot_id,
            reason_code=reason,
        )
        return LoopEvaluation(
            action_effect=action_effect,
            step_completion=self.step_evaluator.evaluate(active_step, report, observation),
            task_completion=task_completion,
        )
