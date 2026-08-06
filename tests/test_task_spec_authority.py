from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from affordance_runtime.contracts import Observation
from affordance_runtime.material_contracts import (
    MaterialBinding,
    MaterialBindingKind,
    MaterialEffectKind,
    MaterialField,
)
from affordance_runtime.progress_evaluation import ProgressEvaluationService
from affordance_runtime.runtime import RunRequest
from affordance_runtime.runtime_evidence import (
    DurableEvidenceStore,
    RecentActionFact,
    RecentActionOutcomeEvidence,
    RecentActionOutcomeEvidenceIndex,
)
from affordance_runtime.source_envelope import SourceEnvelopeBuilder, SourceKind
from affordance_runtime.task_intake import (
    CompilationStatus,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    SemanticValueRelation,
    TaskRequirement,
    TaskRiskPolicy,
    TaskSemanticPayload,
    TaskSpec,
    UserRequest,
)
from affordance_runtime.task_spec_authority import (
    AdmittedTaskSpec,
    MinimalIntentProposal,
    TaskSpecAuthority,
)
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    EvidenceValidityMode,
    OutputSpec,
    SatisfactionMode,
    SuccessExpression,
)
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
)


def _success(requirement_ref: str, criterion_id: str = "criterion:task-complete") -> SuccessExpression:
    return SuccessExpression(
        expression_id=f"success:{criterion_id}",
        operator="criterion",
        criterion_id=criterion_id,
        requirement_refs=(requirement_ref,),
    )


def _high_risk_success(requirement_ref: str) -> SuccessExpression:
    return SuccessExpression(
        expression_id="success:high-risk",
        operator="all_of",
        children=(
            SuccessExpression(
                expression_id="success:external-effect",
                operator="criterion",
                criterion_id="criterion:external-effect",
                requirement_refs=(requirement_ref,),
                policy=CriterionPolicy(
                    satisfaction=SatisfactionMode.ACTION_CAUSED,
                    validity=EvidenceValidityMode.RECENT_ACTION,
                    causal_lineage_required=True,
                ),
            ),
            SuccessExpression(
                expression_id="success:final-recheck",
                operator="criterion",
                criterion_id="criterion:final-recheck",
                requirement_refs=(requirement_ref,),
                policy=CriterionPolicy(
                    validity=EvidenceValidityMode.FINAL_RECHECK,
                    minimum_assurance=AssuranceLevel.AUTHORITATIVE,
                ),
            ),
        ),
    )


def _request_and_envelope():
    request = UserRequest(request_id="authority-request", raw_text="Open account settings")
    return request, SourceEnvelopeBuilder().build(request)


def test_minimal_proposal_requires_typed_success_and_has_no_string_semantic_fallbacks() -> None:
    request, envelope = _request_and_envelope()
    base = {
        "objective": "Open account settings",
        "requested_effects": (
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
    }

    with pytest.raises(ValidationError, match="success"):
        MinimalIntentProposal.model_validate(base)
    with pytest.raises(ValidationError, match="success_criteria"):
        MinimalIntentProposal.model_validate({**base, "success_criteria": ("visible",)})
    with pytest.raises(ValidationError, match="desired_outputs"):
        MinimalIntentProposal.model_validate(
            {**base, "success": _success("requirement:effect:1"), "desired_outputs": ("settings URL",)}
        )
    with pytest.raises(ValidationError, match="evidence_requirements"):
        MinimalIntentProposal.model_validate(
            {**base, "success": _success("requirement:effect:1"), "evidence_requirements": ("DOM proof",)}
        )


def test_authority_converts_invalid_success_policy_construction_to_typed_issue() -> None:
    request, envelope = _request_and_envelope()
    requirement_ref = "requirement:effect:1"
    proposal = MinimalIntentProposal(
        objective="Open account settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=SuccessExpression(
            expression_id="success:conflicting-policy",
            operator="all_of",
            children=(
                SuccessExpression(
                    expression_id="success:conflicting-policy:weak",
                    operator="criterion",
                    criterion_id="criterion:duplicate",
                    requirement_refs=(requirement_ref,),
                    policy=CriterionPolicy(minimum_assurance=AssuranceLevel.WEAK),
                ),
                SuccessExpression(
                    expression_id="success:conflicting-policy:structural",
                    operator="criterion",
                    criterion_id="criterion:duplicate",
                    requirement_refs=(requirement_ref,),
                    policy=CriterionPolicy(minimum_assurance=AssuranceLevel.STRUCTURAL),
                ),
            ),
        ),
    )

    result = TaskSpecAuthority().admit(request=request, envelope=envelope, proposal=proposal)

    assert result.status is CompilationStatus.UNSUPPORTED
    assert tuple(issue.code for issue in result.issues) == ("task_spec_validation_failed",)


def test_taskspec_rejects_semantic_role_mismatch_and_orphan_output_requirement() -> None:
    output_requirement = TaskRequirement(
        requirement_id="requirement:output:1",
        payload=TaskSemanticPayload(kind="output", subject="settings URL"),
        source_anchor_refs=("authority-request:whole_request",),
    )
    success = _success("requirement:output:1")

    for role_field in (
        "allowed_effect_refs",
        "forbidden_effect_refs",
        "hard_constraint_refs",
        "preference_refs",
    ):
        with pytest.raises(ValidationError, match="matching semantic role"):
            TaskSpec(
                task_id=f"role-mismatch:{role_field}",
                revision=1,
                objective="return settings URL",
                operation_class=OperationClass.READ_ONLY,
                requirements=(output_requirement,),
                success=success,
                source_request_ref="authority-request",
                **{role_field: ("requirement:output:1",)},
            )
    with pytest.raises(ValidationError, match="exactly one required OutputSpec"):
        TaskSpec(
            task_id="orphan-output",
            revision=1,
            objective="return settings URL",
            operation_class=OperationClass.READ_ONLY,
            requirements=(output_requirement,),
            success=success,
            source_request_ref="authority-request",
        )


def test_taskspec_rejects_inconsistent_operation_capability_and_risk_aggregates() -> None:
    requirement = TaskRequirement(
        requirement_id="requirement:effect:1",
        payload=TaskSemanticPayload(
            kind="effect",
            subject="settings",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            capability="settings.write",
        ),
        source_anchor_refs=("authority-request:whole_request",),
    )
    base = {
        "task_id": "aggregate-mismatch",
        "revision": 1,
        "objective": "update settings",
        "requirements": (requirement,),
        "allowed_effect_refs": (requirement.requirement_id,),
        "success": _success(requirement.requirement_id),
        "source_request_ref": "authority-request",
    }

    with pytest.raises(ValidationError, match="operation_class"):
        TaskSpec(operation_class=OperationClass.READ_ONLY, capability_ceiling=("settings.write",), **base)
    with pytest.raises(ValidationError, match="capability_ceiling"):
        TaskSpec(operation_class=OperationClass.REVERSIBLE_WRITE, capability_ceiling=(), **base)
    with pytest.raises(ValidationError, match="risk policy"):
        TaskSpec(
            operation_class=OperationClass.REVERSIBLE_WRITE,
            capability_ceiling=("settings.write",),
            risk_policy=TaskRiskPolicy(maximum_operation_class=OperationClass.READ_ONLY),
            **base,
        )


@pytest.mark.parametrize(
    ("kind", "relation", "operation"),
    (
        ("effect", "", OperationClass.REVERSIBLE_WRITE),
        ("effect", "forbidden", OperationClass.READ_ONLY),
        ("constraint", "", OperationClass.READ_ONLY),
        ("preference", "", OperationClass.READ_ONLY),
    ),
)
def test_taskspec_rejects_orphan_canonical_role_requirement(
    kind: str,
    relation: str,
    operation: OperationClass,
) -> None:
    requirement = TaskRequirement(
        requirement_id=f"requirement:{kind}:{relation or 'required'}",
        payload=TaskSemanticPayload(
            kind=kind,  # type: ignore[arg-type]
            subject="semantic role",
            relation=relation,
            operation_class=(operation if kind == "effect" and relation != "forbidden" else None),
        ),
        source_anchor_refs=("authority-request:whole_request",),
    )
    with pytest.raises(ValidationError, match="every canonical role requirement"):
        TaskSpec(
            task_id=f"orphan:{kind}:{relation}",
            revision=1,
            objective="validate complete role coverage",
            operation_class=operation,
            requirements=(requirement,),
            success=_success(requirement.requirement_id),
            source_request_ref="authority-request",
        )


def test_authority_folds_semantic_value_constraint_into_canonical_constraint_requirement() -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Open account settings starting with Acc",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        semantic_value_constraints=(
            SemanticValueConstraint(
                relation=SemanticValueRelation.PREFIX,
                value="Acc",
                target="settings name",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=_success("requirement:effect:1"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.task_spec is not None
    constraint = next(item for item in result.task_spec.requirements if item.payload.kind == "constraint")
    assert constraint.payload.relation == "prefix"
    assert constraint.payload.value == "Acc"
    assert result.task_spec.hard_constraint_refs == (constraint.requirement_id,)
    assert result.task_spec.success.policy is not None
    assert "semantic_value_constraints" not in TaskSpec.model_fields
    assert "evidence_requirements" not in TaskSpec.model_fields


def test_task_spec_authority_is_the_only_proposal_admission_writer() -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Open account settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=_success("requirement:effect:1"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.source_envelope_ref == envelope.identity
    assert result.task_spec.source_binding_digest == envelope.binding_digest
    assert not hasattr(result.task_spec, "source_claims")
    assert not hasattr(result.task_spec, "obligations")
    assert result.task_spec.requirements[0].requirement_id == "requirement:effect:1"
    assert result.admitted_task is not None
    assert result.admitted_task.task_spec is result.task_spec
    assert result.admitted_task.admission_id.startswith("task-admission:v2:")

    with pytest.raises(TypeError):
        RunRequest(task_spec=result.task_spec)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RunRequest()  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="only be issued"):
        AdmittedTaskSpec(result.task_spec, "forged", envelope.identity)


def test_admitted_task_capability_is_not_evicted_by_unrelated_admissions() -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Open account settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=_success("requirement:effect:1"),
    )
    authority = TaskSpecAuthority()
    first = authority.admit(request, envelope, proposal)
    assert first.admitted_task is not None

    for _ in range(1_025):
        assert authority.admit(request, envelope, proposal).admitted_task is not None

    runtime_request = RunRequest(admitted_task=first.admitted_task)
    assert runtime_request.task_spec is first.task_spec


def test_authority_clarifies_success_leaf_with_unadmitted_requirement_ref() -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Open account settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="account settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=_success("requirement:invented"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert {issue.code for issue in result.issues} == {"success_requirement_ref_not_admitted"}


@pytest.mark.parametrize("operation", [OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE])
def test_authority_rejects_effect_without_user_source_anchor(operation) -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Send it",
        requested_effects=(
            RequestedEffect(
                effect_id="effect:unauthorized",
                operation_class=operation,
                material_effect_kind=(
                    MaterialEffectKind.EXTERNAL_ACTION
                    if operation == OperationClass.EXTERNAL_SIDE_EFFECT
                    else MaterialEffectKind.IRREVERSIBLE_ACTION
                ),
                target="external recipient",
                source_ref="observation:invented-authority",
            ),
        ),
        success=_success("effect:unauthorized"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert result.task_spec is None
    assert result.issues[0].code == "unauthorized_external_effect"


def test_direct_explicit_send_is_admitted_without_character_spans() -> None:
    request = UserRequest(request_id="send", raw_text="Send report.pdf to Ada")
    envelope = SourceEnvelopeBuilder().build(request)
    effect = RequestedEffect(
        effect_id="effect:send",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        material_effect_kind=MaterialEffectKind.SEND,
        target="Ada",
        source_ref=envelope.whole_request_anchor.anchor_id,
    )
    bindings = tuple(
        MaterialBinding(
            binding_id=f"binding:{field.value}",
            effect_ref=effect.effect_id,
            field=field,
            value=value,
            source_ref=envelope.whole_request_anchor.anchor_id,
            binding_kind=MaterialBindingKind.DIRECT_USER_EXPLICIT,
        )
        for field, value in (
            (MaterialField.RECIPIENT, "Ada"),
            (MaterialField.EXTERNAL_DESTINATION, "Ada"),
            (MaterialField.FILE, "report.pdf"),
        )
    )
    proposal = MinimalIntentProposal(
        objective=request.raw_text,
        requested_effects=(effect,),
        material_bindings=bindings,
        success=_high_risk_success("effect:send"),
        external_effect_criterion_ids=("criterion:external-effect",),
        final_recheck_criterion_ids=("criterion:final-recheck",),
        required_outputs=(
            OutputSpec(
                output_id="send-receipt",
                materialization_criterion_id="criterion:send-receipt",
            ),
        ),
    )

    incomplete = TaskSpecAuthority().admit(
        request,
        envelope,
        proposal.model_copy(
            update={
                "success": _success("effect:send"),
                "external_effect_criterion_ids": (),
                "final_recheck_criterion_ids": (),
            }
        ),
    )
    assert incomplete.status == CompilationStatus.NEEDS_CLARIFICATION
    assert {item.code for item in incomplete.issues} >= {
        "high_risk_external_criterion_required",
        "high_risk_final_recheck_required",
    }
    assert incomplete.task_spec is None

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert not hasattr(result.task_spec, "material_bindings")
    assert tuple(item.binding_id for item in result.task_spec.inputs) == tuple(item.binding_id for item in bindings)
    assert all(item.material_binding_digest.startswith("sha256:") for item in result.task_spec.inputs)
    assert result.task_spec.external_effect_criterion_ids == ("criterion:external-effect",)
    assert result.task_spec.final_recheck_criterion_ids == ("criterion:final-recheck",)
    assert not {
        "criterion:external-effect",
        "criterion:final-recheck",
    }.intersection(item.criterion_id for item in result.task_spec.criterion_source_bindings)

    recent = RecentActionOutcomeEvidenceIndex()
    recent.append(
        RecentActionOutcomeEvidence(
            outcome_id="outcome:send",
            contract_id="contract:send",
            receipt_ref="receipt:send",
            pre_observation_ref="snapshot:before-send",
            post_observation_ref="snapshot:after-send",
            effect_criterion_ids=("criterion:external-effect",),
            evidence_refs=("evidence:send",),
            effect_satisfied=True,
            facts=(
                RecentActionFact(
                    subject_ref="effect:send",
                    before_value=False,
                    after_value=True,
                    source_kind=EvidenceSourceKind.API_STATE,
                    assurance=AssuranceLevel.AUTHORITATIVE,
                    effect_criterion_ids=("criterion:external-effect",),
                    evidence_refs=("evidence:send",),
                    state_delta_id="delta:send",
                ),
            ),
        )
    )
    observation = Observation(
        "revision:after-send",
        snapshot_id="snapshot:after-send",
        metadata={"output_source_bindings": {"send-receipt": ["resource:send"]}},
    )
    report = VerificationReport(
        VerificationStatus.PASSED,
        [
            VerificationEvidence(
                verifier_kind="http_json",
                target="effect:send",
                passed=True,
                source="api_state",
                observed=True,
                evidence_id="verification:send-final",
                criterion_ids=("criterion:final-recheck", "criterion:send-receipt"),
                environment_revision=observation.environment_revision,
                snapshot_id=observation.snapshot_id,
                strength="authoritative",
            )
        ],
    )
    completion = ProgressEvaluationService().evaluate_task_completion(
        task_spec=result.task_spec,
        state=SimpleNamespace(
            current_contract=SimpleNamespace(id="contract:send"),
            task_progress=SimpleNamespace(
                recent_action_outcomes=recent,
                durable_evidence=DurableEvidenceStore(),
            ),
            uncertain_external_effects=(),
        ),
        observation=observation,
        report=report,
        result={"send-receipt": {"id": "send:1"}},
    )

    assert completion is not None and completion.completed
    assert result.task_spec.required_outputs[0].requirement_ref == "requirement:output:1"
    output_requirement = next(
        item for item in result.task_spec.requirements if item.requirement_id == "requirement:output:1"
    )
    assert output_requirement.payload.kind == "output"
    assert output_requirement.requirement_id != effect.effect_id
    assert result.task_spec.required_outputs[0].source_binding_requirement == tuple(
        item.binding_id for item in result.task_spec.inputs
    )
    assert not {
        "source_claims",
        "obligations",
        "material_bindings",
    }.intersection(type(result.task_spec).model_fields)
    assert result.task_spec.source_binding_digest != envelope.binding_digest
    assert all(anchor.span is None for anchor in envelope.anchors)


def test_material_effect_kind_cannot_downgrade_the_operation_class() -> None:
    request = UserRequest(request_id="downgrade", raw_text="Send report.pdf to Ada")
    envelope = SourceEnvelopeBuilder().build(request)
    proposal = MinimalIntentProposal(
        objective=request.raw_text,
        requested_effects=(
            RequestedEffect(
                effect_id="effect:send",
                operation_class=OperationClass.READ_ONLY,
                material_effect_kind=MaterialEffectKind.SEND,
                target="Ada",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=_success("effect:send"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert any(issue.code == "material_effect_operation_mismatch" for issue in result.issues)


def test_indirect_attachment_recipient_without_exact_or_typed_binding_clarifies() -> None:
    request = UserRequest(
        request_id="attachment-send",
        raw_text="Send the report to the recipient specified in the attached PDF",
        attachment_refs=("attachment:recipient.pdf",),
    )
    envelope = SourceEnvelopeBuilder().build(request)
    effect = RequestedEffect(
        effect_id="effect:send",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        material_effect_kind=MaterialEffectKind.SEND,
        target="recipient in attachment",
        source_ref=envelope.whole_request_anchor.anchor_id,
    )
    proposal = MinimalIntentProposal(
        objective=request.raw_text,
        requested_effects=(effect,),
        material_bindings=(
            MaterialBinding(
                binding_id="binding:file-only",
                effect_ref=effect.effect_id,
                field=MaterialField.FILE,
                value="report",
                source_ref=envelope.whole_request_anchor.anchor_id,
                binding_kind=MaterialBindingKind.DIRECT_USER_EXPLICIT,
            ),
        ),
        success=_success("effect:send"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    missing = {issue.field for issue in result.issues if issue.code == "material_binding_missing"}
    assert "recipient" in missing


def test_payment_amount_anchor_cannot_substitute_for_missing_payee_or_account() -> None:
    request = UserRequest(request_id="payment", raw_text="Pay EUR 500")
    start = request.raw_text.index("500")
    envelope = SourceEnvelopeBuilder().build(
        request,
        exact_anchors=((MaterialField.AMOUNT, start, start + 3),),
    )
    amount_anchor = envelope.anchors[1]
    effect = RequestedEffect(
        effect_id="effect:payment",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        material_effect_kind=MaterialEffectKind.PAYMENT,
        target="payment",
        source_ref=envelope.whole_request_anchor.anchor_id,
    )
    proposal = MinimalIntentProposal(
        objective=request.raw_text,
        requested_effects=(effect,),
        material_bindings=(
            MaterialBinding(
                binding_id="binding:amount",
                effect_ref=effect.effect_id,
                field=MaterialField.AMOUNT,
                value="500",
                source_ref=amount_anchor.anchor_id,
                source_anchor_ref=amount_anchor.anchor_id,
                binding_kind=MaterialBindingKind.EXACT_SOURCE_EXCERPT,
            ),
            MaterialBinding(
                binding_id="binding:currency",
                effect_ref=effect.effect_id,
                field=MaterialField.CURRENCY,
                value="EUR",
                source_ref=envelope.whole_request_anchor.anchor_id,
                binding_kind=MaterialBindingKind.DIRECT_USER_EXPLICIT,
            ),
        ),
        success=_success("effect:payment"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert any(issue.code == "material_binding_missing" and issue.field == "account|payee" for issue in result.issues)


def test_page_source_cannot_create_material_authorization() -> None:
    request = UserRequest(
        request_id="page-authority",
        raw_text="Send report.pdf",
        target_refs=("https://example.invalid/current-page",),
    )
    envelope = SourceEnvelopeBuilder().build(request)
    page_source = next(item for item in envelope.sources if item.kind == SourceKind.TARGET)
    effect = RequestedEffect(
        effect_id="effect:send",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        material_effect_kind=MaterialEffectKind.SEND,
        target="page recipient",
        source_ref=page_source.source_id,
    )
    proposal = MinimalIntentProposal(
        objective=request.raw_text,
        requested_effects=(effect,),
        material_bindings=(
            MaterialBinding(
                binding_id="binding:recipient",
                effect_ref=effect.effect_id,
                field=MaterialField.RECIPIENT,
                value="Ada",
                source_ref=page_source.source_id,
                external_field_ref="dom.recipient",
                binding_kind=MaterialBindingKind.TYPED_EXTERNAL,
            ),
        ),
        success=_success("effect:send"),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert any(issue.code == "observation_cannot_authorize_material_binding" for issue in result.issues)
    assert any(issue.code == "unauthorized_external_effect" for issue in result.issues)
