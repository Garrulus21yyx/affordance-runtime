import pytest

from affordance_runtime.source_envelope import SourceEnvelopeBuilder
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
    assert result.task_spec.source_claims == ()
    assert result.task_spec.obligations == ()


@pytest.mark.parametrize("operation", [OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE])
def test_authority_rejects_effect_without_user_source_anchor(operation) -> None:
    request, envelope = _request_and_envelope()
    proposal = MinimalIntentProposal(
        objective="Send it",
        requested_effects=(
            RequestedEffect(
                operation_class=operation,
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
