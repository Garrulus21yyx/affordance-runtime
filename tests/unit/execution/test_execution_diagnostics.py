from time import perf_counter

from affordance_runtime.execution import (
    ExecutionDiagnosticPhase,
    execution_diagnostic_from_exception,
)


def test_exception_diagnostic_is_total_bounded_and_secret_safe() -> None:
    unusual_error = type("Provider-Timeout", (RuntimeError,), {"__module__": "vendor.<wire>"})
    error = unusual_error(
        "request https://private.example/path token=super-secret\nfailed"
    )

    diagnostic = execution_diagnostic_from_exception(
        error,
        phase=ExecutionDiagnosticPhase.DISPATCH_WAIT,
        started_at=perf_counter(),
        dispatch_crossed=True,
    )

    assert diagnostic.exception_type == "Provider_Timeout"
    assert diagnostic.exception_module == "vendor._wire_"
    assert diagnostic.safe_message == "request <redacted-url> token=<redacted> failed"
    assert diagnostic.traceback_ref.startswith("traceback:sha256:")


def test_repeated_same_exception_occurrences_have_distinct_diagnostic_identity() -> None:
    error = TimeoutError("same timeout")
    first = execution_diagnostic_from_exception(
        error,
        phase=ExecutionDiagnosticPhase.POST_CAPTURE,
        started_at=1.0,
        dispatch_crossed=True,
    )
    second = execution_diagnostic_from_exception(
        error,
        phase=ExecutionDiagnosticPhase.POST_CAPTURE,
        started_at=2.0,
        dispatch_crossed=True,
    )

    assert first.diagnostic_ref != second.diagnostic_ref
    assert first.traceback_ref == second.traceback_ref
