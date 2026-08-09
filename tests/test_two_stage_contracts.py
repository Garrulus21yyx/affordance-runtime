import pytest

from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import (
    DecisionKind,
    PacingConfiguration,
    StageCallCounts,
    TwoStageDecisionIdentity,
)
from affordance_runtime.model_policy.spec import decision_response_schema


def test_decision_kind_values_equal_canonical_discriminators() -> None:
    schema = decision_response_schema()
    canonical = {
        definition["properties"]["type"]["const"]
        for definition in schema["$defs"].values()
        if "type" in definition.get("properties", {})
    }
    assert {item.value for item in DecisionKind} == canonical


def test_logical_identity_is_benchmark_only_bounded_correlation() -> None:
    identity = TwoStageDecisionIdentity(
        "logical:1", "context:1", "routing:1", "payload:1",
    )
    assert identity.context_id == "context:1"
    with pytest.raises(ValueError):
        TwoStageDecisionIdentity("logical:1", "https://private", "routing:1", "payload:1")


def test_call_and_pacing_bounds_forbid_retry_fallback_and_third_call() -> None:
    assert StageCallCounts(1, 1).total_provider_attempts == 2
    for counts in ((2, 0, 0, 0), (1, 2, 0, 0), (1, 1, 1, 0), (1, 1, 0, 1)):
        with pytest.raises(ValueError):
            StageCallCounts(*counts)
    assert PacingConfiguration(7.5, 7.5).inter_stage_delay_s == 7.5
    with pytest.raises(ValueError):
        PacingConfiguration(121, 0)
