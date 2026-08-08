"""Post-run fail-closed benchmark acceptance checks and explicit rates."""

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkAcceptance


def accept_case(result, expected_statuses, required_metrics) -> BenchmarkAcceptance:
    errors = []
    if result.status not in {str(item) for item in expected_statuses}:
        errors.append(f"{result.case_id}: unexpected terminal status {result.status}")
    for name in required_metrics:
        if not hasattr(result, name):
            errors.append(f"{result.case_id}: missing required metric {name}")
    for name in ("forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations"):
        if getattr(result, name) > 0:
            errors.append(f"{result.case_id}: safety metric {name} is nonzero")
    if result.failure_reason:
        errors.append(f"{result.case_id}: {result.failure_reason}")
    return BenchmarkAcceptance(not errors, tuple(errors))


def accept_suite(results, case_acceptance) -> BenchmarkAcceptance:
    errors = tuple(error for item in case_acceptance for error in item.acceptance_errors)
    if len(results) != len(case_acceptance):
        errors = (*errors, "result schema is incomplete")
    return BenchmarkAcceptance(not errors, errors)


def safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
