from __future__ import annotations

import pytest
from pydantic import ValidationError

from affordance_runtime.evaluation_audit import (
    EvaluationBatchStatus,
    EvaluationBatchStop,
    EvaluationRunAudit,
    EvaluationRunIdentity,
    EvaluationStopCategory,
    build_evaluation_run_audit,
    select_unobserved_cases_for_resume,
)


def _identity(*, revision: str = "abc") -> EvaluationRunIdentity:
    return EvaluationRunIdentity.from_dimensions(
        {
            "revision": revision,
            "profile": "strict",
            "model": "local-model",
            "schema": "schema-v1",
            "budget": {"calls": 3},
        }
    )


def test_complete_collection_keeps_runtime_and_external_outcomes_separate() -> None:
    audit = build_evaluation_run_audit(
        identity=_identity(),
        scheduled_case_ids=("case-a", "case-b", "case-c"),
        observed_case_ids=("case-a", "case-b", "case-c"),
        failed_case_ids=("case-b", "case-c"),
        runtime_failed_case_ids=("case-b",),
        external_failed_case_ids=("case-c",),
    )

    assert audit.status == EvaluationBatchStatus.COMPLETE
    assert audit.collection_closed
    assert audit.comparable
    assert audit.repair_selection_ready
    assert (audit.failed_count, audit.runtime_failed_count, audit.external_failed_count) == (2, 1, 1)
    assert [item.disposition for item in audit.cases] == [
        "observed_passed",
        "observed_failed",
        "observed_failed",
    ]


def test_ordinary_case_failures_do_not_make_collection_incomplete_or_invalid() -> None:
    audit = build_evaluation_run_audit(
        identity=_identity(),
        scheduled_case_ids=("case-a", "case-b"),
        observed_case_ids=("case-a", "case-b"),
        failed_case_ids=("case-a", "case-b"),
        runtime_failed_case_ids=("case-a",),
        external_failed_case_ids=("case-b",),
    )

    assert audit.status == EvaluationBatchStatus.COMPLETE
    assert audit.invalidated_count == 0
    assert audit.unrun_count == 0


def test_interrupted_collection_resumes_only_unobserved_cases_with_same_identity() -> None:
    identity = _identity()
    audit = build_evaluation_run_audit(
        identity=identity,
        scheduled_case_ids=("case-a", "case-b", "case-c"),
        observed_case_ids=("case-a",),
        failed_case_ids=(),
        runtime_failed_case_ids=(),
        external_failed_case_ids=(),
        interrupted=True,
    )

    assert audit.status == EvaluationBatchStatus.INCOMPLETE_RESUMABLE
    assert audit.resume_allowed
    assert not audit.repair_selection_ready
    assert select_unobserved_cases_for_resume(
        stored_identity=identity,
        requested_identity=_identity(),
        audit=audit,
    ) == ("case-b", "case-c")
    with pytest.raises(ValueError, match="exact immutable identity"):
        select_unobserved_cases_for_resume(
            stored_identity=identity,
            requested_identity=_identity(revision="changed"),
            audit=audit,
        )


def test_integrity_stop_invalidates_every_case_and_forbids_resume() -> None:
    audit = build_evaluation_run_audit(
        identity=_identity(),
        scheduled_case_ids=("case-a", "case-b"),
        observed_case_ids=("case-a",),
        failed_case_ids=("case-a",),
        runtime_failed_case_ids=("case-a",),
        external_failed_case_ids=(),
        stop=EvaluationBatchStop(
            category=EvaluationStopCategory.RESULT_INTEGRITY,
            reason="result ledger cannot be written reliably",
            invalidates_observed_results=True,
            resume_allowed=False,
        ),
    )

    assert audit.status == EvaluationBatchStatus.INVALIDATED
    assert audit.invalidated_count == audit.scheduled_count == 2
    assert not audit.comparable
    assert not audit.repair_selection_ready
    assert [item.disposition for item in audit.cases] == [
        "invalidated_observed",
        "invalidated_unobserved",
    ]
    with pytest.raises(ValueError, match="not eligible"):
        select_unobserved_cases_for_resume(
            stored_identity=_identity(),
            requested_identity=_identity(),
            audit=audit,
        )


def test_provider_stop_can_preserve_prior_cases_and_resume_unobserved_cases() -> None:
    audit = build_evaluation_run_audit(
        identity=_identity(),
        scheduled_case_ids=("case-a", "case-b"),
        observed_case_ids=("case-a",),
        failed_case_ids=("case-a",),
        runtime_failed_case_ids=("case-a",),
        external_failed_case_ids=(),
        stop=EvaluationBatchStop(
            category=EvaluationStopCategory.PROVIDER_INFRASTRUCTURE,
            reason="profile-wide provider unavailable",
            invalidates_observed_results=False,
            resume_allowed=True,
        ),
    )

    assert audit.status == EvaluationBatchStatus.INCOMPLETE_RESUMABLE
    assert audit.comparable
    assert audit.resume_allowed
    assert not audit.repair_selection_ready


def test_stop_on_last_case_is_not_misreported_as_complete_evidence() -> None:
    audit = build_evaluation_run_audit(
        identity=_identity(),
        scheduled_case_ids=("case-a",),
        observed_case_ids=("case-a",),
        failed_case_ids=("case-a",),
        runtime_failed_case_ids=("case-a",),
        external_failed_case_ids=(),
        stop=EvaluationBatchStop(
            category=EvaluationStopCategory.SAFETY_AUTHORITY,
            reason="authority boundary violated",
            invalidates_observed_results=False,
            resume_allowed=False,
        ),
    )

    assert audit.collection_closed
    assert audit.comparable
    assert audit.status == EvaluationBatchStatus.STOPPED
    assert not audit.repair_selection_ready
    assert not audit.resume_allowed


def test_accounting_rejects_unknown_duplicate_and_unexplained_failures() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_evaluation_run_audit(
            identity=_identity(),
            scheduled_case_ids=("case-a", "case-a"),
            observed_case_ids=(),
            failed_case_ids=(),
            runtime_failed_case_ids=(),
            external_failed_case_ids=(),
        )
    with pytest.raises(ValueError, match="outside"):
        build_evaluation_run_audit(
            identity=_identity(),
            scheduled_case_ids=("case-a",),
            observed_case_ids=("case-b",),
            failed_case_ids=(),
            runtime_failed_case_ids=(),
            external_failed_case_ids=(),
        )
    with pytest.raises(ValueError, match="explained"):
        build_evaluation_run_audit(
            identity=_identity(),
            scheduled_case_ids=("case-a",),
            observed_case_ids=("case-a",),
            failed_case_ids=("case-a",),
            runtime_failed_case_ids=(),
            external_failed_case_ids=(),
        )


def test_identity_and_serialized_audit_are_tamper_evident() -> None:
    identity = _identity()
    with pytest.raises(ValidationError, match="digest mismatch"):
        EvaluationRunIdentity(
            canonical_dimensions=identity.canonical_dimensions,
            digest="sha256:" + "0" * 64,
        )
    audit = build_evaluation_run_audit(
        identity=identity,
        scheduled_case_ids=("case-a",),
        observed_case_ids=("case-a",),
        failed_case_ids=(),
        runtime_failed_case_ids=(),
        external_failed_case_ids=(),
    )
    assert EvaluationRunAudit.model_validate_json(audit.model_dump_json()) == audit
    with pytest.raises(ValidationError, match="does not match case ledger"):
        EvaluationRunAudit.model_validate({**audit.model_dump(), "observed_count": 0})


@pytest.mark.parametrize(
    ("dimension", "changed"),
    [
        ("revision", "def"),
        ("profile", "compatibility"),
        ("registry", "registry-v2"),
        ("prompt", "prompt-v2"),
        ("model", "other-model"),
        ("schema", "schema-v2"),
        ("budget", {"calls": 4}),
    ],
)
def test_identity_digest_binds_every_frozen_dimension(
    dimension: str,
    changed: object,
) -> None:
    dimensions = {
        "revision": "abc",
        "profile": "strict",
        "registry": "registry-v1",
        "prompt": "prompt-v1",
        "model": "local-model",
        "schema": "schema-v1",
        "budget": {"calls": 3},
    }
    baseline = EvaluationRunIdentity.from_dimensions(dimensions)

    assert EvaluationRunIdentity.from_dimensions(
        {**dimensions, dimension: changed}
    ).digest != baseline.digest


def test_invalidating_stop_cannot_claim_same_evidence_set_is_resumable() -> None:
    with pytest.raises(ValidationError, match="cannot resume"):
        EvaluationBatchStop(
            category=EvaluationStopCategory.COMPARABILITY,
            reason="version drift",
            invalidates_observed_results=True,
            resume_allowed=True,
        )
