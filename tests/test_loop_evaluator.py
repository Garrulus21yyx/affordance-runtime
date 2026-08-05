from affordance_runtime.contracts import ExecutionReceipt, Observation
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.verification.contracts import (
    CriterionStatus,
    TaskCompletionEvaluation,
)
from affordance_runtime.verification.loop_evaluator import LoopEvaluator
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
)


def test_receipt_action_effect_step_and_task_are_distinct_typed_results() -> None:
    refs = (SourceReference("request", "request:step"),)
    step = StepSpec(
        step_id="step:save",
        objective="Save the setting",
        interaction=ElementIntent("settings", refs),
        completion_criteria=(
            StateCriterion(
                criterion_id="criterion:step:save",
                source_refs=refs,
                subject="settings",
                relation=StateCriterionRelation.IS_COMPLETED,
                evidence_policy=CriterionEvidencePolicy(
                    EvidenceStrength.INDEPENDENT,
                    ("dom_state",),
                ),
            ),
        ),
        source_refs=refs,
    )
    receipt = ExecutionReceipt(
        "contract:save", "dom", True, "revision:1", "revision:2", 1.0
    )
    observation = Observation(
        "revision:2", snapshot_id="snapshot:2", page_revision="page:2"
    )
    report = VerificationReport(
        VerificationStatus.PASSED,
        [
            VerificationEvidence(
                "receipt",
                "dispatch",
                True,
                "receipt",
                evidence_id="receipt:1",
                criterion_ids=("criterion:step:save",),
                environment_revision="revision:2",
                snapshot_id="snapshot:2",
                strength="strong",
            )
        ],
    )
    task_completion = TaskCompletionEvaluation(
        status=CriterionStatus.UNSATISFIED,
        root_criterion_id="success:task",
    )

    result = LoopEvaluator().evaluate(
        receipt=receipt,
        report=report,
        observation=observation,
        active_step=step,
        task_completion=task_completion,
    )

    assert receipt.success is True
    assert result.action_effect.status == CriterionStatus.UNKNOWN
    assert result.step_completion.status == CriterionStatus.UNKNOWN
    assert result.task_completion.status == CriterionStatus.UNSATISFIED
