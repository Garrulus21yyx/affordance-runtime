from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
    safe_boundary_identity,
    safe_exception_class,
)
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.world import AcquisitionOrigin, AcquisitionStatus


@given(st.lists(st.sampled_from((
    "reset_returned",
    "capture_returned",
    "capture_threw",
    "execute_not_sent",
    "execute_sent",
    "execute_threw",
)), min_size=1, max_size=40))
def test_accounting_is_the_sum_of_legal_exactly_once_receipts(specs) -> None:
    accounting = RunAccounting()
    receipts = []
    for index, spec in enumerate(specs, 1):
        receipt = _legal_receipt(index, spec)
        accounting.record(receipt)
        receipts.append(receipt)
    assert accounting.observation_attempts == sum(item.acquisition_attempts for item in receipts)
    assert accounting.execution_attempts == sum(item.execution_attempts for item in receipts)
    assert accounting.currentness_probes == sum(item.currentness_probe_count for item in receipts)
    assert accounting.effectful_dispatches == sum(item.effectful_dispatches for item in receipts)
    assert accounting.receipt_count == len(receipts)


def test_same_receipt_cannot_be_accounted_twice() -> None:
    accounting = RunAccounting()
    receipt = AttemptReceipt(
        "attempt:1", AttemptOperation.CAPTURE, "wait_refresh",
        AcquisitionOrigin.INDEPENDENT_CAPTURE, AcquisitionOrigin.INDEPENDENT_CAPTURE,
        AttemptDisposition.RETURNED, "capture_acquired", 1, 0, 0, 0,
        acquisition_status=AcquisitionStatus.ACQUIRED,
    )
    accounting.record(receipt)
    try:
        accounting.record(receipt)
    except ValueError as exc:
        assert "already" in str(exc)
    else:
        raise AssertionError("duplicate receipt was accepted")


def test_accounting_rejects_noncontiguous_attempt_identity_at_its_owner() -> None:
    accounting = RunAccounting()
    receipt = AttemptReceipt(
        "attempt:999",
        AttemptOperation.CAPTURE,
        "wait_refresh",
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        None,
        AttemptDisposition.RETURNED,
        "independent_capture_unsupported",
        0,
        0,
        0,
        0,
        acquisition_status=AcquisitionStatus.CAPABILITY_UNAVAILABLE,
    )

    with pytest.raises(ValueError, match="next run-scoped sequence"):
        accounting.record(receipt)


@given(st.text().filter(lambda value: "\x00" not in value))
def test_foreign_exception_class_is_normalized_to_a_bounded_private_token(name: str) -> None:
    error = type(name, (Exception,), {})("private exception detail")
    normalized = safe_exception_class(error)
    receipt = AttemptReceipt(
        "attempt:1", AttemptOperation.CAPTURE, "wait_refresh",
        AcquisitionOrigin.INDEPENDENT_CAPTURE, None,
        AttemptDisposition.THREW, "capture_exception", 1, 0, 0, 0,
        exception_class=normalized,
        acquisition_status=AcquisitionStatus.FAILED,
    )
    assert receipt.exception_class == normalized
    assert 0 < len(normalized) <= 128
    assert normalized.replace("_", "").isalnum()
    assert "private exception detail" not in normalized


@given(st.text(), st.text(), st.sampled_from(("request", "backend")))
def test_foreign_boundary_identity_retains_only_equality_or_opaque_digest(
    actual: str, expected: str, kind: str,
) -> None:
    normalized = safe_boundary_identity(actual, expected, kind=kind)
    if actual == expected and kind == "request":
        assert normalized == expected
    else:
        assert normalized.startswith(f"{kind}_sha256_")
        assert len(normalized) == len(kind) + 8 + 64
        assert normalized != actual


def test_reset_receipt_rejects_physically_impossible_counts() -> None:
    with pytest.raises(ValueError, match="physical operation matrix"):
        AttemptReceipt(
            "attempt:999",
            AttemptOperation.RESET,
            "reset",
            AcquisitionOrigin.RESET,
            AcquisitionOrigin.RESET,
            AttemptDisposition.RETURNED,
            "reset_acquired",
            1,
            2,
            2,
            0,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        )


@pytest.mark.parametrize(
    ("attempts", "origin"),
    ((0, AcquisitionOrigin.POST_ACTION), (1, None)),
)
def test_acquired_execute_requires_one_physical_post_action_acquisition(
    attempts, origin,
) -> None:
    with pytest.raises(ValueError, match="status matrix"):
        AttemptReceipt(
            "attempt:999",
            AttemptOperation.EXECUTE,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
            origin,
            AttemptDisposition.RETURNED,
            "post_action_acquired",
            attempts,
            1,
            1,
            0,
            DispatchStatus.SENT,
            "request:one",
            "request:one",
            True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        )


def test_valid_execute_lineage_requires_matching_request_identity() -> None:
    with pytest.raises(ValueError, match="matching request identity"):
        AttemptReceipt(
            "attempt:999",
            AttemptOperation.EXECUTE,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
            AcquisitionOrigin.POST_ACTION,
            AttemptDisposition.RETURNED,
            "post_action_acquired",
            1,
            1,
            1,
            0,
            DispatchStatus.SENT,
            "request:expected",
            "request:actual",
            True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        )


def _legal_receipt(index: int, spec: str) -> AttemptReceipt:
    attempt_id = f"attempt:{index}"
    if spec == "reset_returned":
        return AttemptReceipt(
            attempt_id, AttemptOperation.RESET, "reset", AcquisitionOrigin.RESET,
            AcquisitionOrigin.RESET, AttemptDisposition.RETURNED, "reset_acquired",
            1, 0, 0, 0, acquisition_status=AcquisitionStatus.ACQUIRED,
        )
    if spec == "capture_returned":
        return AttemptReceipt(
            attempt_id, AttemptOperation.CAPTURE, "wait_refresh",
            AcquisitionOrigin.INDEPENDENT_CAPTURE,
            AcquisitionOrigin.INDEPENDENT_CAPTURE, AttemptDisposition.RETURNED,
            "capture_acquired", 1, 0, 0, 0,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        )
    if spec == "capture_threw":
        return AttemptReceipt(
            attempt_id, AttemptOperation.CAPTURE, "wait_refresh",
            AcquisitionOrigin.INDEPENDENT_CAPTURE, None, AttemptDisposition.THREW,
            "capture_exception", 1, 0, 0, 0, exception_class="RuntimeError",
            acquisition_status=AcquisitionStatus.FAILED,
        )
    if spec == "execute_threw":
        return AttemptReceipt(
            attempt_id, AttemptOperation.EXECUTE, "execute",
            AcquisitionOrigin.POST_ACTION, None, AttemptDisposition.THREW,
            "execute_exception", 0, 1, 0, 0,
            expected_request_id=f"request:{index}", exception_class="RuntimeError",
        )
    dispatch = (
        DispatchStatus.NOT_SENT if spec == "execute_not_sent" else DispatchStatus.SENT
    )
    return AttemptReceipt(
        attempt_id, AttemptOperation.EXECUTE, "post_action",
        AcquisitionOrigin.POST_ACTION,
        None if dispatch is DispatchStatus.NOT_SENT else AcquisitionOrigin.POST_ACTION,
        AttemptDisposition.RETURNED,
        "action_not_dispatched" if dispatch is DispatchStatus.NOT_SENT else "post_action_acquired",
        0 if dispatch is DispatchStatus.NOT_SENT else 1,
        1,
        int(dispatch is not DispatchStatus.NOT_SENT), 0, dispatch,
        f"request:{index}", f"request:{index}", True,
        acquisition_status=(
            None if dispatch is DispatchStatus.NOT_SENT else AcquisitionStatus.ACQUIRED
        ),
    )
