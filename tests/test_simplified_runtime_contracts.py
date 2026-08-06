from __future__ import annotations

import pytest

from affordance_runtime.simplified_runtime_contracts import (
    ActionOutcome,
    ActionOutcomeStatus,
    CompositeCriterion,
    CompositeCriterionOperator,
    CriterionEvidencePolicy,
    ElementIntent,
    ElementOperationKind,
    EvidenceStrength,
    ExecutionAttempt,
    ObservationIdentity,
    PresenceCriterion,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
    TaskPlanView,
    VerificationResult,
    VerificationStatus,
    interaction_for_state,
)
from runtime_test_support import legacy_step_spec


def _source(source_id: str = "source:user:1") -> SourceReference:
    return SourceReference(source_id=source_id, source_unit_id="unit:1")


def _policy() -> CriterionEvidencePolicy:
    return CriterionEvidencePolicy(
        minimum_strength=EvidenceStrength.INDEPENDENT,
        allowed_source_kinds=("dom_state",),
    )


def _observation(snapshot_id: str = "snapshot:pre") -> ObservationIdentity:
    return ObservationIdentity(
        snapshot_id=snapshot_id,
        page_revision="page:1",
        environment_revision="env:1",
    )


def test_completion_criterion_requires_source_and_rejects_mutable_value() -> None:
    with pytest.raises(ValueError, match="source refs"):
        PresenceCriterion(
            criterion_id="criterion:submit-visible",
            subject="semantic:submit",
            relation=StateCriterionRelation.IS_VISIBLE,
            evidence_policy=_policy(),
            source_refs=(),
        )

    with pytest.raises(ValueError, match="immutable"):
        StateCriterion(
            criterion_id="criterion:field-value",
            subject="semantic:field",
            relation=StateCriterionRelation.EQUALS,
            expected_value={"value": ["Alice"]},
            evidence_policy=_policy(),
            source_refs=(_source(),),
        )


def test_criterion_rejects_unknown_relation() -> None:
    with pytest.raises(ValueError, match="unsupported relation"):
        StateCriterion(
            criterion_id="criterion:bad",
            subject="semantic:field",
            relation="regex_execute",  # type: ignore[arg-type]
            expected_value="Alice",
            evidence_policy=_policy(),
            source_refs=(_source(),),
        )


@pytest.mark.parametrize("subject", ("browser:textbox", "application:textbox"))
def test_qualified_element_role_projects_to_fail_closed_role_grounding(subject: str) -> None:
    interaction = interaction_for_state(
        subject,
        StateCriterionRelation.IS_COMPLETED,
        None,
        (_source(),),
        interaction_operation="focus",
    )

    assert interaction == ElementIntent(
        "textbox",
        (_source(),),
        role="textbox",
        match_by_role=True,
        operation=ElementOperationKind.FOCUS,
    )


def test_composite_criterion_rejects_self_cycle() -> None:
    with pytest.raises(ValueError, match="cycle"):
        CompositeCriterion(
            criterion_id="criterion:all",
            operator=CompositeCriterionOperator.ALL_OF,
            child_criterion_ids=("criterion:all",),
            source_refs=(_source(),),
        )


def test_step_spec_rejects_legacy_criterion_at_canonical_ingress() -> None:
    precondition = PresenceCriterion(
        criterion_id="criterion:button-precondition",
        subject="semantic:submit",
        relation=StateCriterionRelation.IS_AVAILABLE,
        evidence_policy=_policy(),
        source_refs=(_source(),),
        role="precondition",
    )

    with pytest.raises(TypeError, match="canonical CriterionExpr"):
        StepSpec(
            step_id="step:submit",
            objective="Submit the form",
            interaction=ElementIntent("semantic:submit", (_source(),)),
            completion_criteria=(precondition,),
            source_refs=(_source(),),
        )


def test_task_plan_view_is_identity_exact_and_deeply_immutable() -> None:
    step = legacy_step_spec(
        step_id="step:type-name",
        objective="Type the name",
        interaction=ElementIntent("semantic:name", (_source(),)),
        completion_criteria=(
            StateCriterion(
                criterion_id="criterion:name",
                subject="semantic:name",
                relation=StateCriterionRelation.EQUALS,
                expected_value="Alice",
                evidence_policy=_policy(),
                source_refs=(_source(),),
            ),
        ),
        source_refs=(_source(),),
    )
    view = TaskPlanView(
        plan_id="plan:1",
        plan_version=1,
        task_spec_identity="task:sha256",
        task_revision=1,
        steps=(step,),
        active_step_id="step:type-name",
    )

    assert view.step_ids == ("step:type-name",)
    with pytest.raises(AttributeError):
        view.steps[0].completion_criteria = ()  # type: ignore[misc]


def test_action_outcome_requires_matching_attempt_and_verification_identity() -> None:
    attempt = ExecutionAttempt(
        attempt_id="attempt:1",
        contract_id="contract:1",
        contract_hash="hash:contract",
        issued_at_state_version=7,
        action_kind="type_text",
        semantic_target_id="semantic:name",
        pre_observation=_observation("snapshot:pre"),
    )
    stale_verification = VerificationResult(
        status=VerificationStatus.PASSED,
        contract_id="contract:2",
        contract_hash="hash:contract",
        pre_snapshot_id="snapshot:pre",
        post_observation=_observation("snapshot:post"),
        verified_criterion_ids=("criterion:name",),
        evidence_refs=("evidence:1",),
    )

    with pytest.raises(ValueError, match="contract"):
        ActionOutcome(
            outcome_id="outcome:1",
            attempt=attempt,
            verification=stale_verification,
            status=ActionOutcomeStatus.VERIFIED_EFFECT,
            step_id="step:type-name",
        )
