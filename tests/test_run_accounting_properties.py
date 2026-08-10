from __future__ import annotations

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


@given(
    st.lists(
        st.tuples(
            st.sampled_from(tuple(AttemptOperation)),
            st.sampled_from(tuple(AttemptDisposition)),
            st.integers(min_value=0, max_value=2),
            st.integers(min_value=0, max_value=2),
            st.integers(min_value=0, max_value=3),
        ),
        min_size=1,
        max_size=40,
    )
)
def test_accounting_is_the_sum_of_exactly_once_receipts(specs) -> None:
    accounting = RunAccounting()
    receipts = []
    for index, (operation, disposition, acquisitions, executions, probes) in enumerate(specs, 1):
        receipt = AttemptReceipt(
            f"attempt:{index}", operation, "", None, None, disposition,
            "bounded_reason", acquisitions, executions, executions, probes,
        )
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
        "attempt:one", AttemptOperation.CAPTURE, "wait_refresh", None, None,
        AttemptDisposition.RETURNED, "capture_acquired", 1, 0, 0, 0,
    )
    accounting.record(receipt)
    try:
        accounting.record(receipt)
    except ValueError as exc:
        assert "already" in str(exc)
    else:
        raise AssertionError("duplicate receipt was accepted")


@given(st.text().filter(lambda value: "\x00" not in value))
def test_foreign_exception_class_is_normalized_to_a_bounded_private_token(name: str) -> None:
    error = type(name, (Exception,), {})("private exception detail")
    normalized = safe_exception_class(error)
    receipt = AttemptReceipt(
        "attempt:one", AttemptOperation.CAPTURE, "wait_refresh", None, None,
        AttemptDisposition.THREW, "capture_exception", 1, 0, 0, 0,
        exception_class=normalized,
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
