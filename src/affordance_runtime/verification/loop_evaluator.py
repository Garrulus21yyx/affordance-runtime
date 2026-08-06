"""Loop-native composition of distinct action, step, and task evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.contracts import ExecutionReceipt
from affordance_runtime.runtime_evidence import RecentActionOutcomeEvidence
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    LoopEvaluation,
    PredicateEvidence,
    PredicateEvidenceContext,
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
        observation: UnifiedObservation,
        active_step: StepSpec | None,
        task_completion: TaskCompletionEvaluation | None,
        recent_action_outcomes: tuple[RecentActionOutcomeEvidence, ...] = (),
        current_evidence: tuple[PredicateEvidence, ...] = (),
        durable_evidence: tuple[PredicateEvidence, ...] = (),
        latest_final_recheck_ref: str = "",
        current_resource_versions: tuple[tuple[str, str], ...] = (),
    ) -> LoopEvaluation:
        independent = tuple(
            item
            for item in report.evidence
            if item.source not in {"receipt", "execution_receipt"} and item.strength in {"strong", "authoritative"}
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
            step_completion=self.step_evaluator.evaluate(
                active_step,
                self.evidence_context(
                    observation=observation,
                    current_contract_id=receipt.contract_id,
                    recent_action_outcomes=recent_action_outcomes,
                    current_evidence=current_evidence,
                    durable_evidence=durable_evidence,
                    latest_final_recheck_ref=latest_final_recheck_ref,
                    current_resource_versions=current_resource_versions,
                ),
            ),
            task_completion=task_completion,
        )

    @staticmethod
    def evidence_context(
        *,
        observation: UnifiedObservation,
        current_contract_id: str = "",
        recent_action_outcomes: tuple[RecentActionOutcomeEvidence, ...] = (),
        current_evidence: tuple[PredicateEvidence, ...] = (),
        durable_evidence: tuple[PredicateEvidence, ...] = (),
        latest_final_recheck_ref: str = "",
        current_resource_versions: tuple[tuple[str, str], ...] = (),
    ) -> PredicateEvidenceContext:
        causal = tuple(
            PredicateEvidence(
                evidence_ref=fact.evidence_refs[0],
                subject_ref=fact.subject_ref,
                observed_value=fact.after_value,
                source_kind=fact.source_kind,
                assurance=fact.assurance,
                observation_ref=item.post_observation_ref,
                contract_id=item.contract_id,
                receipt_ref=item.receipt_ref,
                pre_observation_ref=item.pre_observation_ref,
                post_observation_ref=item.post_observation_ref,
                effect_criterion_ids=fact.effect_criterion_ids,
                runtime_causal_lineage=True,
            )
            for item in recent_action_outcomes
            if item.effect_satisfied
            for fact in item.facts
        )
        return PredicateEvidenceContext(
            current_observation_ref=observation.snapshot_id,
            evidence=(*current_evidence, *causal, *durable_evidence),
            current_observation=observation,
            current_contract_id=current_contract_id,
            latest_final_recheck_ref=latest_final_recheck_ref,
            current_resource_versions=current_resource_versions,
            recent_evidence_refs=frozenset(item.evidence_ref for item in causal),
            recent_contract_ids=frozenset(item.contract_id for item in recent_action_outcomes),
            durable_evidence_refs=frozenset(item.evidence_ref for item in durable_evidence),
        )
