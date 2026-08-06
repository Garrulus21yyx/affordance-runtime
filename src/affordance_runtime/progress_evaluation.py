"""Task and post-action evaluation projection for the Progress façade."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, cast

from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.contracts import Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.runtime_evidence import observation_predicate_evidence, semantic_progress_fingerprint
from affordance_runtime.stage_protocol import RuntimeEventBuffer
from affordance_runtime.verification.contracts import TaskCompletionEvaluation
from affordance_runtime.verification.loop_evaluator import LoopEvaluator
from affordance_runtime.verification.mechanical import VerificationReport
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator
from affordance_runtime.verification_report_adapter import (
    admit_completion_evidence,
    output_source_bindings,
)


class ActionEffectEvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


class ActiveStepEvaluationStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NOT_EVALUATED = "not_evaluated"


class TaskCompletionEvaluationStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class PostActionEvaluation:
    contract_id: str
    action_effect: ActionEffectEvaluationStatus
    active_step: ActiveStepEvaluationStatus
    task_completion: TaskCompletionEvaluationStatus
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    progress_committed: bool = False
    liveness_decision: str = ""


def _runtime_final_recheck_ref(
    report: VerificationReport | None,
    observation: Observation,
) -> str:
    if report is None:
        return ""
    authoritative = any(
        item.source in {"external_evaluator", "independent_http_json", "api_state"}
        and item.strength in {"strong", "authoritative"}
        for item in report.evidence
    )
    return f"runtime-final-recheck:{observation.snapshot_id}" if authoritative else ""


@dataclass(frozen=True)
class ProgressEvaluationService:
    def evaluate_task_completion(
        self,
        *,
        task_spec: object | None,
        state: Any,
        observation: Observation,
        report: VerificationReport | None,
        result: dict[str, object],
    ) -> TaskCompletionEvaluation | None:
        if task_spec is None:
            return None
        typed_task_spec = cast(Any, task_spec)
        task_progress = getattr(state, "task_progress", None)
        latest_final_recheck_ref = _runtime_final_recheck_ref(report, observation)
        evidence_context = LoopEvaluator.evidence_context(
            observation=cast(Any, observation),
            current_contract_id=(
                str(state.current_contract.id) if getattr(state, "current_contract", None) is not None else ""
            ),
            recent_action_outcomes=(
                tuple(task_progress.recent_action_outcomes.records) if task_progress is not None else ()
            ),
            current_evidence=observation_predicate_evidence(cast(Any, observation)),
            durable_evidence=(tuple(task_progress.durable_evidence.records) if task_progress is not None else ()),
            latest_final_recheck_ref=latest_final_recheck_ref,
        )
        admitted = admit_completion_evidence(
            task_spec=typed_task_spec,
            observation=observation,
            evidence_context=evidence_context,
            report=report,
        )
        retained = getattr(state, "completion_criterion_evaluations", {})
        relevant_ids = TaskCompletionEvaluator.criterion_ids(typed_task_spec)
        final_recheck_ids = frozenset(typed_task_spec.final_recheck_criterion_ids)
        for evaluation in admitted:
            if evaluation.criterion_id in relevant_ids and evaluation.criterion_id not in final_recheck_ids:
                retained[evaluation.criterion_id] = evaluation
        current_index = {item.criterion_id: item for item in admitted}
        criterion_results = tuple(
            current_index.get(criterion_id, evaluation) for criterion_id, evaluation in retained.items()
        ) + tuple(evaluation for criterion_id, evaluation in current_index.items() if criterion_id not in retained)
        return TaskCompletionEvaluator().evaluate(
            task_spec=typed_task_spec,
            criterion_results=criterion_results,
            result_payload=result,
            output_source_bindings=output_source_bindings(observation),
            uncertain_external_effects=tuple(
                str(item) for item in getattr(state, "uncertain_external_effects", ()) if str(item)
            ),
        )

    @staticmethod
    def record_task_completion(
        events: RuntimeEventBuffer,
        state: Any,
        evaluation: TaskCompletionEvaluation,
    ) -> None:
        events.add(
            "TaskCompletionEvaluated",
            {
                "state": state.phase,
                "status": evaluation.status.value,
                "root_criterion_id": evaluation.root_criterion_id,
                "missing_required_outputs": list(evaluation.missing_required_outputs),
                "missing_rechecks": list(evaluation.missing_rechecks),
                "constraint_violations": list(evaluation.constraint_violations),
                "uncertain_external_effects": list(evaluation.uncertain_external_effects),
            },
        )

    @staticmethod
    def record_post_action(
        events: RuntimeEventBuffer,
        state: Any,
        report: VerificationReport,
        *,
        contract_id: str,
        active_step_status: ActiveStepEvaluationStatus,
        task_completion_status: TaskCompletionEvaluationStatus,
        progress_committed: bool,
        liveness_decision: str,
    ) -> PostActionEvaluation:
        criterion_ids = tuple(
            dict.fromkeys(criterion_id for evidence in report.evidence for criterion_id in evidence.criterion_ids)
        )
        requirement_ids = tuple(
            dict.fromkeys(requirement_id for evidence in report.evidence for requirement_id in evidence.requirement_ids)
        )
        evidence_refs = tuple(
            dict.fromkeys(evidence.evidence_id for evidence in report.evidence if evidence.evidence_id)
        )
        evaluation = PostActionEvaluation(
            contract_id=contract_id,
            action_effect=(
                ActionEffectEvaluationStatus.PASSED
                if report.passed
                else ActionEffectEvaluationStatus(report.status.value)
            ),
            active_step=active_step_status,
            task_completion=task_completion_status,
            criterion_ids=criterion_ids,
            requirement_ids=requirement_ids,
            evidence_refs=evidence_refs,
            progress_committed=progress_committed,
            liveness_decision=liveness_decision,
        )
        events.add(
            "PostActionEvaluated",
            {
                "state": state.phase,
                "contract_id": evaluation.contract_id,
                "action_effect_status": evaluation.action_effect.value,
                "active_step_status": evaluation.active_step.value,
                "task_completion_status": evaluation.task_completion.value,
                "criterion_ids": list(evaluation.criterion_ids),
                "requirement_ids": list(evaluation.requirement_ids),
                "evidence_refs": list(evaluation.evidence_refs),
                "evidence": [asdict(item) for item in report.evidence],
                "progress_committed": progress_committed,
                "liveness_decision": liveness_decision,
            },
        )
        return evaluation

    @staticmethod
    def verification_failure(
        *,
        run_id: str,
        task_spec: Any,
        state: Any,
        action: Any,
        report: VerificationReport,
        verification_ref: ArtifactRef | None,
        remaining_budgets: RemainingRecoveryBudgets,
    ) -> Any:
        plan = state.task_plan
        return make_failure_envelope(
            run_id=run_id,
            phase=FailurePhase.VERIFICATION,
            failure_class=FailureClass.VERIFICATION,
            error_code=RuntimeErrorCode.VERIFICATION_FAILED,
            message=report.reason or RuntimeErrorCode.VERIFICATION_FAILED.value,
            state_version=state.version,
            task_revision=(
                plan.task_revision if plan is not None else task_spec.revision if task_spec is not None else 1
            ),
            plan_version=plan.plan_version if plan is not None else 0,
            active_step_id=(state.task_progress.active_step_id if state.task_progress is not None else ""),
            observation_epoch_id=state.current_snapshot_id,
            snapshot_id=state.current_snapshot_id,
            contract=action.contract,
            receipt=action.receipt,
            expected_effect=action.contract.intent,
            evidence_refs=((verification_ref.path,) if verification_ref else ()),
            verification_ref=verification_ref.path if verification_ref else "",
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=((state.current_disproved_assumption,) if state.current_disproved_assumption else ()),
            remaining_budgets=remaining_budgets,
            progress_fingerprint=semantic_progress_fingerprint(state),
        )
