import pytest

from affordance_runtime.obligation_attribution import (
    AttributionTargetView,
    EvidenceSourceKind,
    EvidenceStrength,
    PostActionEvidenceNormalizer,
    ProgressAttributionTicket,
    VerificationEvidenceView,
    VerificationReportView,
    VerifierSemanticEvidenceDeclaration,
)
from affordance_runtime.task_intake import TaskObligationRelation


def _ticket() -> ProgressAttributionTicket:
    return ProgressAttributionTicket(
        ticket_id="ticket:abc",
        task_spec_identity="sha256:task",
        task_revision=3,
        issued_at_state_version=17,
        contract_id="contract-1",
        contract_hash="sha256:contract-1",
        semantic_target_id="semantic:slider",
        action_kind="press_key",
        candidate_obligation_ids=("obligation:slider",),
        pre_snapshot_id="snapshot-pre",
        pre_page_revision="page-pre",
        pre_environment_revision="env-pre",
    )


def _evidence(
    evidence_id: str = "evidence:slider",
    *,
    target: str = "semantic:slider",
    passed: bool = True,
    source: str = "post_action_observation",
    observed: object = 7,
    expected: object = 7,
    snapshot_id: str = "snapshot-post",
    environment_revision: str = "env-post",
    strength: str = "strong",
) -> VerificationEvidenceView:
    return VerificationEvidenceView(
        verifier_kind="control_state",
        target=target,
        passed=passed,
        source=source,
        observed=observed,
        expected=expected,
        evidence_id=evidence_id,
        criterion_ids=("criterion:slider",),
        requirement_ids=("requirement:slider",),
        snapshot_id=snapshot_id,
        environment_revision=environment_revision,
        observed_at_s=1.25,
        reported_strength=strength,
    )


def _report(*evidence: VerificationEvidenceView, status: str = "passed") -> VerificationReportView:
    return VerificationReportView(status=status, evidence=evidence, reason="")


def _declaration(
    evidence_id: str = "evidence:slider",
    *,
    subject: str = "semantic:slider",
    relation: TaskObligationRelation = TaskObligationRelation.EQUALS,
    before_value: object | None = None,
    expected_value: object | None = 7,
    minimum_strength: EvidenceStrength = EvidenceStrength.INDEPENDENT,
    allowed_sources: tuple[EvidenceSourceKind, ...] = (
        EvidenceSourceKind.POST_ACTION_OBSERVATION,
    ),
) -> VerifierSemanticEvidenceDeclaration:
    return VerifierSemanticEvidenceDeclaration(
        evidence_id=evidence_id,
        evidence_subject_id=subject,
        relation=relation,
        before_value=before_value,
        expected_value=expected_value,
        minimum_strength=minimum_strength,
        allowed_source_kinds=allowed_sources,
    )


def _normalize(
    *,
    ticket: ProgressAttributionTicket | None = None,
    report: VerificationReportView | None = None,
    declarations: tuple[VerifierSemanticEvidenceDeclaration, ...] | None = None,
    post_snapshot_id: str = "snapshot-post",
    post_page_revision: str = "page-post",
    post_environment_revision: str = "env-post",
):
    return PostActionEvidenceNormalizer().normalize(
        ticket=ticket or _ticket(),
        report=report or _report(_evidence()),
        declarations=(_declaration(),) if declarations is None else declarations,
        post_snapshot_id=post_snapshot_id,
        post_page_revision=post_page_revision,
        post_environment_revision=post_environment_revision,
    )


def test_normalizes_control_state_equals_fact_with_identity() -> None:
    result = _normalize()

    assert result.status == "normalized"
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.contract_id == "contract-1"
    assert fact.contract_hash == "sha256:contract-1"
    assert fact.pre_snapshot_id == "snapshot-pre"
    assert fact.post_snapshot_id == "snapshot-post"
    assert fact.action_semantic_target_id == "semantic:slider"
    assert fact.evidence_subject_id == "semantic:slider"
    assert fact.relation == TaskObligationRelation.EQUALS
    assert fact.after_value == 7
    assert fact.expected_value == 7
    assert fact.source_kind == EvidenceSourceKind.POST_ACTION_OBSERVATION
    assert fact.strength == EvidenceStrength.INDEPENDENT
    assert fact.evidence_refs == ("evidence:slider",)
    assert fact.criterion_ids == ("criterion:slider",)
    assert fact.requirement_ids == ("requirement:slider",)


def test_normalizes_has_changed_and_checked_facts() -> None:
    changed = _normalize(
        report=_report(_evidence(observed=7, expected=7)),
        declarations=(
            _declaration(
                relation=TaskObligationRelation.HAS_CHANGED,
                before_value=5,
                expected_value=7,
            ),
        ),
    )
    checked = _normalize(
        report=_report(_evidence("evidence:checkbox", target="semantic:checkbox", observed=True)),
        declarations=(
            _declaration(
                "evidence:checkbox",
                subject="semantic:checkbox",
                relation=TaskObligationRelation.IS_CHECKED,
                expected_value=True,
            ),
        ),
    )

    assert changed.status == "normalized"
    assert changed.facts[0].before_value == 5
    assert changed.facts[0].after_value == 7
    assert checked.status == "normalized"
    assert checked.facts[0].after_value is True


def test_independent_api_can_be_authoritative_and_multiple_facts_are_allowed() -> None:
    result = _normalize(
        report=_report(
            _evidence("evidence:api-a", source="independent_http_json", observed="done", expected="done"),
            _evidence("evidence:api-b", source="independent_http_json", observed=True, expected=True),
        ),
        declarations=(
            _declaration(
                "evidence:api-a",
                relation=TaskObligationRelation.EQUALS,
                expected_value="done",
                minimum_strength=EvidenceStrength.AUTHORITATIVE,
                allowed_sources=(EvidenceSourceKind.INDEPENDENT_API,),
            ),
            _declaration(
                "evidence:api-b",
                relation=TaskObligationRelation.IS_COMPLETED,
                expected_value=True,
                minimum_strength=EvidenceStrength.AUTHORITATIVE,
                allowed_sources=(EvidenceSourceKind.INDEPENDENT_API,),
            ),
        ),
    )

    assert result.status == "normalized"
    assert tuple(fact.evidence_refs[0] for fact in result.facts) == (
        "evidence:api-a",
        "evidence:api-b",
    )
    assert all(fact.strength == EvidenceStrength.AUTHORITATIVE for fact in result.facts)


def test_report_view_freezes_evidence_and_rejects_mutable_values() -> None:
    source = [_evidence()]
    report = VerificationReportView(status="passed", evidence=source, reason="")
    source.append(_evidence("evidence:late"))

    assert len(report.evidence) == 1
    with pytest.raises(ValueError, match="unsupported observed evidence value"):
        _evidence(observed={"value": 7})


def test_failed_stale_weak_or_unsupported_evidence_does_not_normalize() -> None:
    assert _normalize(report=_report(_evidence(), status="failed")).status == "report_not_passed"
    assert _normalize(report=_report(_evidence(passed=False))).status == "no_eligible_evidence"
    assert (
        _normalize(
            report=_report(_evidence(snapshot_id="snapshot-other")),
        ).status
        == "stale"
    )
    assert (
        _normalize(
            report=_report(_evidence(source="external_evaluator")),
            declarations=(
                _declaration(
                    allowed_sources=(EvidenceSourceKind.POST_ACTION_OBSERVATION,),
                ),
            ),
        ).status
        == "no_eligible_evidence"
    )
    assert (
        _normalize(
            report=_report(_evidence(source="execution_receipt")),
            declarations=(
                _declaration(
                    allowed_sources=(EvidenceSourceKind.EXECUTION_RECEIPT,),
                ),
            ),
        ).status
        == "no_eligible_evidence"
    )
    assert (
        _normalize(
            report=_report(_evidence(observed=True, expected=True)),
            declarations=(
                _declaration(
                    relation=TaskObligationRelation.EQUALS,
                    expected_value=True,
                ),
            ),
        ).status
        == "unsupported_observed_shape"
    )


def test_invalid_inputs_fail_closed() -> None:
    assert _normalize(declarations=()).status == "invalid"
    assert (
        _normalize(
            report=_report(_evidence(), _evidence()),
        ).status
        == "invalid"
    )
    assert (
        _normalize(
            declarations=(
                _declaration(),
                _declaration(),
            ),
        ).status
        == "invalid"
    )
    with pytest.raises(ValueError, match="candidate obligation ids cannot be empty"):
        ProgressAttributionTicket(
            ticket_id="ticket:empty",
            task_spec_identity="sha256:task",
            task_revision=3,
            issued_at_state_version=17,
            contract_id="contract-1",
            contract_hash="sha256:contract-1",
            semantic_target_id="semantic:slider",
            action_kind="press_key",
            candidate_obligation_ids=(),
            pre_snapshot_id="snapshot-pre",
            pre_page_revision="page-pre",
            pre_environment_revision="env-pre",
        )
    with pytest.raises(ValueError, match="canonical subject ids cannot be empty"):
        AttributionTargetView(
            semantic_target_id="semantic:slider",
            canonical_subject_ids=(),
        )
