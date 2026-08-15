import pytest

from affordance_runtime.benchmarks.model_conformance.two_stage.qualification import (
    TwoStageDiagnosticConclusion,
    diagnose_two_stage,
)


@pytest.mark.parametrize(("rates", "expected"), (
    ((0.8, 1, 0.8, 0.8, 0), TwoStageDiagnosticConclusion.ROUTING_BOTTLENECK),
    ((1, 0.8, 0.8, 0.8, 0), TwoStageDiagnosticConclusion.PAYLOAD_BOTTLENECK),
    ((1, 1, 1, 0.8, 0), TwoStageDiagnosticConclusion.COUPLING_BOTTLENECK),
    ((1, 1, 0.8, 0.8, 0), TwoStageDiagnosticConclusion.HANDOFF_BOTTLENECK),
    ((1, 1, 1, 1, 0), TwoStageDiagnosticConclusion.TWO_STAGE_UNNECESSARY),
    ((0.8, 0.8, 0.8, 0.8, 0), TwoStageDiagnosticConclusion.PROFILE_UNSUITABLE),
    ((1, 1, 1, 1, 0.5), TwoStageDiagnosticConclusion.PROVIDER_AVAILABILITY_INCONCLUSIVE),
))
def test_each_diagnostic_conclusion(rates, expected) -> None:
    assert diagnose_two_stage(
        routing_rate=rates[0], payload_rate=rates[1], end_to_end_rate=rates[2],
        single_stage_rate=rates[3], provider_unavailable_rate=rates[4],
    ) is expected
