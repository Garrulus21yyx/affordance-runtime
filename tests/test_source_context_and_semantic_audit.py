import pytest

from affordance_runtime.material_contracts import MaterialEffectKind, MaterialField
from affordance_runtime.semantic_audit import (
    SemanticAudit,
    SemanticAuditStatus,
)
from affordance_runtime.source_context import SourceContextConsumer, SourceContextProjector
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import CompilationStatus, OperationClass, RequestedEffect, UserRequest
from affordance_runtime.task_spec_authority import MinimalIntentProposal, TaskSpecAuthority


def _proposal(envelope, operation=OperationClass.READ_ONLY):
    return MinimalIntentProposal(
        objective="Inspect settings",
        requested_effects=(
            RequestedEffect(
                effect_id="effect:settings" if operation == OperationClass.IRREVERSIBLE else "",
                operation_class=operation,
                material_effect_kind=(
                    MaterialEffectKind.DELETE if operation == OperationClass.IRREVERSIBLE else MaterialEffectKind.NONE
                ),
                target="settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success_criteria=("settings are visible",),
    )


def test_audit_only_flags_trigger_while_authority_owns_material_completeness() -> None:
    low_request = UserRequest(request_id="low", raw_text="Inspect settings")
    low_envelope = SourceEnvelopeBuilder().build(low_request)
    high_request = UserRequest(request_id="high", raw_text="Delete it")
    high_envelope = SourceEnvelopeBuilder().build(high_request)
    audit = SemanticAudit()

    low = audit.evaluate(low_envelope, _proposal(low_envelope))
    high = audit.evaluate(
        high_envelope,
        _proposal(high_envelope, OperationClass.IRREVERSIBLE),
    )

    assert low.triggered is False
    assert low.status == SemanticAuditStatus.PASS
    assert high.triggered is True
    assert high.status == SemanticAuditStatus.PASS
    assert high.trigger_reasons == ("irreversible_effect",)

    admitted = TaskSpecAuthority().admit(
        high_request,
        high_envelope,
        _proposal(high_envelope, OperationClass.IRREVERSIBLE),
    )
    assert admitted.status == CompilationStatus.NEEDS_CLARIFICATION
    assert {issue.code for issue in admitted.issues} == {"material_binding_missing"}


def test_execution_consumer_cannot_obtain_source_context() -> None:
    request = UserRequest(request_id="context", raw_text="Inspect settings")
    envelope = SourceEnvelopeBuilder().build(request)
    admitted = TaskSpecAuthority().admit(request, envelope, _proposal(envelope))
    assert admitted.task_spec is not None
    task_spec = admitted.task_spec

    try:
        SourceContextProjector().project(
            request,
            envelope,
            task_spec,
            consumer="executor",  # type: ignore[arg-type]
            anchor_ids=(envelope.whole_request_anchor.anchor_id,),
        )
    except PermissionError as exc:
        assert "source context consumer is not allowed" in str(exc)
    else:
        raise AssertionError("execution obtained raw source context")

    view = SourceContextProjector().project(
        request,
        envelope,
        task_spec,
        consumer=SourceContextConsumer.TASK_PLANNER,
        anchor_ids=(envelope.whole_request_anchor.anchor_id,),
        requirement_ids=(task_spec.requirements[0].requirement_id,),
    )
    assert view.context_only is True
    assert view.requirement_ids == (task_spec.requirements[0].requirement_id,)
    assert view.excerpts[0].content == request.raw_text
    assert view.source_binding_digest == task_spec.source_binding_digest


def test_source_context_rejects_anchor_from_an_unrequested_requirement() -> None:
    raw_text = "Open alpha then inspect beta"
    request = UserRequest(request_id="bound-context", raw_text=raw_text)
    alpha_start = raw_text.index("alpha")
    beta_start = raw_text.index("beta")
    envelope = SourceEnvelopeBuilder().build(
        request,
        exact_anchors=(
            (MaterialField.RESOURCE, alpha_start, alpha_start + len("alpha")),
            (MaterialField.FILE, beta_start, beta_start + len("beta")),
        ),
    )
    alpha_anchor, beta_anchor = envelope.anchors[1:]
    proposal = MinimalIntentProposal(
        objective=raw_text,
        requested_effects=(
            RequestedEffect(
                effect_id="effect:alpha",
                operation_class=OperationClass.NAVIGATION,
                target="alpha",
                source_ref=alpha_anchor.anchor_id,
            ),
            RequestedEffect(
                effect_id="effect:beta",
                operation_class=OperationClass.READ_ONLY,
                target="beta",
                source_ref=beta_anchor.anchor_id,
            ),
        ),
        success_criteria=("alpha opened", "beta inspected"),
    )
    admitted = TaskSpecAuthority().admit(request, envelope, proposal)
    assert admitted.task_spec is not None

    with pytest.raises(PermissionError, match="not bound"):
        SourceContextProjector().project(
            request,
            envelope,
            admitted.task_spec,
            consumer=SourceContextConsumer.TASK_PLANNER,
            anchor_ids=(beta_anchor.anchor_id,),
            requirement_ids=("effect:alpha",),
        )
