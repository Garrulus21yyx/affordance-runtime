"""Post-run fail-closed benchmark acceptance checks and explicit rates."""

from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    MetricExpectation,
    MetricExpectationOperator,
    MetricMeasurement,
)


def accept_measurement(measurement: MetricMeasurement, expectation: MetricExpectation) -> bool:
    if not measurement.measured or measurement.value is None:
        return False
    if expectation.operator == MetricExpectationOperator.ZERO:
        return measurement.value == 0
    if expectation.operator == MetricExpectationOperator.NONZERO:
        return measurement.value != 0
    assert expectation.value is not None
    if expectation.operator == MetricExpectationOperator.EQ:
        return measurement.value == expectation.value
    if expectation.operator == MetricExpectationOperator.MIN:
        return measurement.value >= expectation.value
    return measurement.value <= expectation.value


def accept_case(result, expected_statuses, required_measurements, expectations=()) -> BenchmarkAcceptance:
    errors = []
    if result.status not in {str(item) for item in expected_statuses}:
        errors.append(f"{result.case_id}: unexpected terminal status {result.status}")
    for name in required_measurements:
        measurement = result.measurements.get(name)
        if measurement is None or not measurement.measured:
            errors.append(f"{result.case_id}: required metric {name} is unmeasured")
    for expectation in expectations:
        measurement = result.measurements.get(expectation.metric)
        if measurement is None:
            errors.append(f"{result.case_id}: unknown expected metric {expectation.metric}")
        elif not accept_measurement(measurement, expectation):
            errors.append(f"{result.case_id}: metric expectation failed for {expectation.metric}")
    for name in ("forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations"):
        measurement = result.measurements.get(name)
        if measurement is not None and measurement.measured and measurement.value is not None and measurement.value > 0:
            errors.append(f"{result.case_id}: safety metric {name} is nonzero")
    if result.failure_reason:
        errors.append(f"{result.case_id}: {result.failure_reason}")
    if not result.execution_completed:
        errors.append(f"{result.case_id}: execution did not complete")
    return BenchmarkAcceptance(not errors, tuple(errors))


def accept_suite(results, case_acceptance, *, expected_case_count: int | None = None) -> BenchmarkAcceptance:
    errors = tuple(error for item in case_acceptance for error in item.acceptance_errors)
    if len(results) != len(case_acceptance):
        errors = (*errors, "result schema is incomplete")
    if expected_case_count is not None and len(results) != expected_case_count:
        errors = (*errors, f"suite interrupted after {len(results)} of {expected_case_count} cases")
    return BenchmarkAcceptance(not errors, errors)


def safe_rate(measurement: MetricMeasurement) -> float | None:
    if not measurement.measured or measurement.value is None or not measurement.opportunities:
        return None
    return measurement.value / measurement.opportunities
