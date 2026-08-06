import pytest

from affordance_runtime.material_contracts import (
    MaterialBinding,
    MaterialBindingKind,
    MaterialEffectKind,
    MaterialField,
)
from affordance_runtime.source_envelope import SourceEnvelopeBuilder, SourceKind
from affordance_runtime.task_intake import (
    CompilationStatus,
    OperationClass,
    RequestedEffect,
    UserRequest,
)
from affordance_runtime.task_spec_authority import (
    MinimalIntentProposal,
    TaskSpecAuthority,
)
from affordance_runtime.verification.contracts import OutputSpec


def _request_and_envelope():
    request = UserRequest(request_id="authority-request", raw_text="Open account settings")
    return request, SourceEnvelopeBuilder().build(request)


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
        success_criteria=("account settings are visible",),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.source_envelope_ref == envelope.identity
    assert result.task_spec.source_binding_digest == envelope.binding_digest
    assert not hasattr(result.task_spec, "source_claims")
    assert not hasattr(result.task_spec, "obligations")
    assert result.task_spec.requirements[0].requirement_id == "requirement:effect:1"


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
        success_criteria=("message is sent",),
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
        success_criteria=("message is sent",),
        required_outputs=(
            OutputSpec(
                output_id="send-receipt",
                materialization_criterion_id="criterion:send-receipt",
            ),
        ),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert not hasattr(result.task_spec, "material_bindings")
    assert tuple(item.binding_id for item in result.task_spec.inputs) == tuple(item.binding_id for item in bindings)
    assert all(item.material_binding_digest.startswith("sha256:") for item in result.task_spec.inputs)
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
        success_criteria=("message is sent",),
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
        success_criteria=("message is sent",),
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
        success_criteria=("payment is committed",),
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
        success_criteria=("message is sent",),
    )

    result = TaskSpecAuthority().admit(request, envelope, proposal)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert any(issue.code == "observation_cannot_authorize_material_binding" for issue in result.issues)
    assert any(issue.code == "unauthorized_external_effect" for issue in result.issues)
