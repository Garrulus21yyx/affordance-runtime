from affordance_runtime.task_intake import (
    IntentDraft,
    OperationClass,
    RequestedEffect,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    UserRequest,
)
from affordance_runtime.task_obligation_coverage import (
    TaskObligationCoverageReview,
    TaskObligationCoverageStatus,
    validate_task_obligation_coverage_review,
)


def _request() -> UserRequest:
    return UserRequest(
        request_id="request-coverage",
        raw_text="Read the current code, enter it in the destination, then submit.",
    )


def _draft() -> IntentDraft:
    read_claim = SourcedTaskClaim(
        claim_id="claim-read",
        kind=TaskClaimKind.DEPENDENCY,
        statement="read current code",
        source_ref="request-coverage",
    )
    submit_claim = SourcedTaskClaim(
        claim_id="claim-submit",
        kind=TaskClaimKind.TERMINAL,
        statement="submit destination code",
        source_ref="request-coverage",
    )
    return IntentDraft(
        objective="Read, enter, and submit the code",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="destination code",
                source_ref="request-coverage",
            ),
        ),
        candidate_success_criteria=("destination code submitted",),
        candidate_source_claims=(read_claim, submit_claim),
        candidate_obligations=(
            TaskObligationSpec(
                obligation_id="obligation-read",
                kind=TaskObligationKind.PREDICATE,
                subject="current code",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source="observation",
                claim_ids=(read_claim.claim_id,),
                evidence_requirements=("fresh current-code observation",),
            ),
            TaskObligationSpec(
                obligation_id="obligation-submit",
                kind=TaskObligationKind.EFFECT,
                subject="destination code",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=(submit_claim.claim_id,),
                depends_on=("obligation-read",),
                evidence_requirements=("fresh submission evidence",),
                terminal=True,
            ),
        ),
    )


def test_complete_review_must_cover_every_required_claim() -> None:
    decision = validate_task_obligation_coverage_review(
        _request(),
        _draft(),
        TaskObligationCoverageReview(
            status=TaskObligationCoverageStatus.COMPLETE,
            covered_claim_ids=("claim-read",),
        ),
    )

    assert decision.status == TaskObligationCoverageStatus.UNSUPPORTED
    assert decision.issue_code == "coverage_review_incomplete_claim_set"


def test_coverage_review_rejects_nonliteral_request_quote() -> None:
    decision = validate_task_obligation_coverage_review(
        _request(),
        _draft(),
        TaskObligationCoverageReview(
            status=TaskObligationCoverageStatus.UNSUPPORTED,
            uncovered_source_quotes=("invented clause",),
        ),
    )

    assert decision.status == TaskObligationCoverageStatus.UNSUPPORTED
    assert decision.issue_code == "coverage_review_invalid_quote"


def test_coverage_review_projects_ambiguous_dependency_to_clarification() -> None:
    decision = validate_task_obligation_coverage_review(
        _request(),
        _draft(),
        TaskObligationCoverageReview(
            status=TaskObligationCoverageStatus.NEEDS_CLARIFICATION,
            unresolved_dependency_quotes=("current code",),
        ),
    )

    assert decision.status == TaskObligationCoverageStatus.NEEDS_CLARIFICATION
    assert decision.issue_code == "unresolved_task_dependency"
    assert decision.issue_detail == "current code"
