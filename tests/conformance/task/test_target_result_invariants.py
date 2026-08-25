import pytest

from affordance_runtime.execution import (
    ActionError,
    ActionResult,
    DispatchStatus,
    ExecutionTransition,
)
from affordance_runtime.surfaces.wot.contracts import WotTransportResult, WotTransportStatus


@pytest.mark.parametrize(
    ("status", "success", "error"),
    (
        (DispatchStatus.NOT_SENT, True, ActionError.EXECUTION_FAILED),
        (DispatchStatus.NOT_SENT, False, None),
        (DispatchStatus.SENT_UNKNOWN, True, ActionError.EXECUTION_FAILED),
        (DispatchStatus.SENT_UNKNOWN, False, None),
        (DispatchStatus.SENT, True, ActionError.EXECUTION_FAILED),
        (DispatchStatus.SENT, False, None),
    ),
)
def test_action_result_rejects_inconsistent_dispatch_state(status, success, error) -> None:
    with pytest.raises(ValueError, match="dispatch status"):
        ActionResult("request", status, "fixture", success, error)


def test_action_result_allows_sent_business_failure() -> None:
    result = ActionResult(
        "request",
        DispatchStatus.SENT,
        "fixture",
        False,
        ActionError.EXECUTION_FAILED,
    )
    assert not result.transport_success


def test_causal_transition_requires_a_successful_sent_action() -> None:
    assert (
        ActionResult(
            "request",
            DispatchStatus.SENT,
            "fixture",
            True,
            causal_transition=ExecutionTransition.STABLE_NAVIGATION,
        ).causal_transition
        is ExecutionTransition.STABLE_NAVIGATION
    )
    with pytest.raises(ValueError, match="causal transition"):
        ActionResult(
            "request",
            DispatchStatus.NOT_SENT,
            "fixture",
            False,
            ActionError.EXECUTION_FAILED,
            causal_transition=ExecutionTransition.STABLE_NAVIGATION,
        )


@pytest.mark.parametrize(
    ("status", "success", "error_type"),
    (
        (WotTransportStatus.NOT_SENT, True, "failure"),
        (WotTransportStatus.SENT_UNKNOWN, True, "failure"),
        (WotTransportStatus.SENT, True, "failure"),
        (WotTransportStatus.SENT, False, ""),
    ),
)
def test_wot_transport_result_rejects_inconsistent_status(status, success, error_type) -> None:
    with pytest.raises(ValueError, match="transport status"):
        WotTransportResult(status, success, error_type)
