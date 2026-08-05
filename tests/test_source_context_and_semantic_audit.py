from affordance_runtime.semantic_audit import (
    SemanticAudit,
    SemanticAuditStatus,
)
from affordance_runtime.source_context import SourceContextConsumer, SourceContextProjector
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import OperationClass, RequestedEffect, UserRequest
from affordance_runtime.task_spec_authority import MinimalIntentProposal


def _proposal(envelope, operation=OperationClass.READ_ONLY):
    return MinimalIntentProposal(
        objective="Inspect settings",
        requested_effects=(
            RequestedEffect(
                operation_class=operation,
                target="settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success_criteria=("settings are visible",),
    )


def test_low_risk_audit_is_skipped_and_high_risk_missing_scope_clarifies() -> None:
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
    assert high.status == SemanticAuditStatus.CLARIFICATION_REQUIRED
    assert high.trigger_reasons == ("irreversible_effect",)


def test_execution_consumer_cannot_obtain_source_context() -> None:
    request = UserRequest(request_id="context", raw_text="Inspect settings")
    envelope = SourceEnvelopeBuilder().build(request)

    try:
        SourceContextProjector().project(
            request,
            envelope,
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
        consumer=SourceContextConsumer.TASK_PLANNER,
        anchor_ids=(envelope.whole_request_anchor.anchor_id,),
    )
    assert view.context_only is True
    assert view.excerpts[0].content == request.raw_text
