import pytest

from affordance_runtime.contracts import ExecutionReceipt
from affordance_runtime.criteria import LiteralValue, PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.runtime_evidence import RecentActionFact, RecentActionOutcomeEvidence
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    CriterionStatus,
    EvidenceSourceKind,
    SatisfactionMode,
    TaskCompletionEvaluation,
)
from affordance_runtime.verification.loop_evaluator import LoopEvaluator
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
)
from runtime_test_support import legacy_step_spec


def test_receipt_action_effect_step_and_task_are_distinct_typed_results() -> None:
    refs = (SourceReference("request", "request:step"),)
    step = legacy_step_spec(
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
    receipt = ExecutionReceipt("contract:save", "dom", True, "revision:1", "revision:2", 1.0)
    observation = UnifiedObservation(
        snapshot_id="snapshot:2",
        page_revision="page:2",
        environment_revision="revision:2",
        observed_text="",
        targets=(),
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


@pytest.mark.parametrize(
    ("operator", "expected", "after_value", "source_kind"),
    (
        (
            PredicateOperator.EQUALS,
            "enabled",
            "enabled",
            EvidenceSourceKind.WOT_PROPERTY_STATE,
        ),
        (
            PredicateOperator.CONTAINS,
            "done",
            "job-done",
            EvidenceSourceKind.API_STATE,
        ),
    ),
)
def test_cross_surface_causality_preserves_after_value_and_source(
    operator,
    expected,
    after_value,
    source_kind,  # noqa: ANN001
) -> None:
    refs = (SourceReference("request", "request:step"),)
    criterion = PredicateExpr(
        "criterion:effect",
        SubjectExpr("resource", "resource:setting"),
        operator,
        CriterionPolicy(
            satisfaction=SatisfactionMode.ACTION_CAUSED,
            minimum_assurance=AssuranceLevel.AUTHORITATIVE,
            allowed_source_kinds=(source_kind,),
            causal_lineage_required=True,
        ),
        LiteralValue(expected),
    )
    step = StepSpec(
        "step:effect",
        "Apply resource effect",
        ElementIntent("resource:setting", refs),
        (criterion,),
        refs,
        ("requirement:test",),
    )
    fact = RecentActionFact(
        "resource:setting",
        "disabled",
        after_value,
        source_kind,
        AssuranceLevel.AUTHORITATIVE,
        (criterion.criterion_id,),
        ("evidence:effect",),
        "delta:effect",
    )
    outcome = RecentActionOutcomeEvidence(
        "outcome:effect",
        "contract:effect",
        "receipt:effect",
        "snapshot:1",
        "snapshot:2",
        (criterion.criterion_id,),
        ("evidence:effect",),
        True,
        (fact,),
    )
    result = LoopEvaluator().evaluate(
        receipt=ExecutionReceipt("contract:effect", source_kind.value, True, "revision:1", "revision:2", 1.0),
        report=VerificationReport(VerificationStatus.INCONCLUSIVE),
        observation=UnifiedObservation(
            snapshot_id="snapshot:2",
            page_revision="page:2",
            environment_revision="revision:2",
            observed_text="",
            targets=(),
        ),
        active_step=step,
        task_completion=None,
        recent_action_outcomes=(outcome,),
    )
    assert result.step_completion.status == CriterionStatus.SATISFIED
    assert result.step_completion.evidence_refs == ("evidence:effect",)
