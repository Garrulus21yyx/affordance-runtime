import pytest

from affordance_runtime.benchmarks.target_loop.acceptance import accept_measurement, safe_rate
from affordance_runtime.benchmarks.target_loop.contracts import (
    MetricExpectation,
    MetricExpectationOperator,
    MetricMeasurement,
)


def test_metric_measurement_distinguishes_zero_unmeasured_and_no_opportunities() -> None:
    zero = MetricMeasurement(0, measured=True, opportunities=1)
    unavailable = MetricMeasurement(None, measured=False)
    no_opportunities = MetricMeasurement(0, measured=True, opportunities=0)

    assert zero.value == 0 and zero.measured
    assert unavailable.value is None and not unavailable.measured
    assert safe_rate(no_opportunities) is None


@pytest.mark.parametrize(
    ("operator", "expected", "accepted"),
    [
        (MetricExpectationOperator.EQ, 2, True),
        (MetricExpectationOperator.MIN, 2, True),
        (MetricExpectationOperator.MAX, 2, True),
        (MetricExpectationOperator.ZERO, None, False),
        (MetricExpectationOperator.NONZERO, None, True),
    ],
)
def test_typed_metric_expectations(operator, expected, accepted) -> None:
    expectation = MetricExpectation("executions", operator, expected)
    assert accept_measurement(MetricMeasurement(2, True), expectation) is accepted


def test_unmeasured_required_metric_fails_closed() -> None:
    expectation = MetricExpectation("stale_zero_call_violations", MetricExpectationOperator.ZERO)
    assert not accept_measurement(MetricMeasurement(None, False), expectation)
