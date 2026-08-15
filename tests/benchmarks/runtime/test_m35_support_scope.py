from affordance_runtime.benchmarks.model_conformance.classification import (
    ModelPolicyCapabilityStatus,
    classify_policy_capabilities,
)
from affordance_runtime.benchmarks.model_conformance.contracts import ModelConformanceStage


def _twenty() -> dict[str, tuple[int, int]]:
    return {str(level): (20, 20) for level in range(5)}


def test_l0_l4_only_grants_action_selection_scope() -> None:
    support = classify_policy_capabilities(
        _twenty(), (), support_attestation=True, recurrent_matrix=None,
    )
    assert support.structured_output_status is ModelPolicyCapabilityStatus.SUPPORTED
    assert support.action_selection_status is ModelPolicyCapabilityStatus.SUPPORTED
    assert support.full_recurrent_decision_status is ModelPolicyCapabilityStatus.NOT_ADMITTED


def test_full_recurrent_support_requires_every_runtime_decision_twenty_of_twenty() -> None:
    complete = {variant: (20, 20) for variant in (
        "select_action", "request_evidence", "request_action_page", "ask_user",
        "propose_done", "wait", "abort",
    )}
    partial = {**complete, "wait": (19, 20)}
    assert classify_policy_capabilities(
        _twenty(), (), support_attestation=True, recurrent_matrix=partial,
    ).full_recurrent_decision_status is ModelPolicyCapabilityStatus.PARTIAL
    assert classify_policy_capabilities(
        _twenty(), (), support_attestation=True, recurrent_matrix=complete,
        critical_matrix_passed=True,
    ).full_recurrent_decision_status is ModelPolicyCapabilityStatus.SUPPORTED


def test_provider_unavailable_is_inconclusive_not_semantic_failure() -> None:
    support = classify_policy_capabilities(
        {}, (ModelConformanceStage.UNAVAILABLE,), support_attestation=False,
        recurrent_matrix=None,
    )
    assert support.full_recurrent_decision_status is ModelPolicyCapabilityStatus.INCONCLUSIVE_PROVIDER_AVAILABILITY
