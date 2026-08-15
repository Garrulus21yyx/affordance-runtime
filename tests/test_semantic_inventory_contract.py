from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
)
from affordance_runtime.world.semantic_inventory import (
    MAX_SEMANTIC_INVENTORY_COUNT,
    SemanticInventoryStatus,
    SemanticInventorySummary,
)


@given(
    projected=st.integers(min_value=0, max_value=1_000),
    omitted=st.integers(min_value=0, max_value=1_000),
    actionable_fraction=st.floats(min_value=0, max_value=1, allow_nan=False),
    informational_fraction=st.floats(min_value=0, max_value=1, allow_nan=False),
)
def test_assessed_inventory_is_a_closed_conserved_algebra(
    projected: int,
    omitted: int,
    actionable_fraction: float,
    informational_fraction: float,
) -> None:
    recognized = projected + omitted
    actionable = int(projected * actionable_fraction)
    non_executable = projected - actionable
    informational = int(non_executable * informational_fraction)

    summary = SemanticInventorySummary.assessed(
        "fixture-profile.v1",
        recognized_target_count=recognized,
        projected_target_count=projected,
        actionable_target_count=actionable,
        non_executable_target_count=non_executable,
        omitted_target_count=omitted,
        informational_target_count=informational,
    )

    assert summary.recognized_target_count == projected + omitted
    assert summary.projected_target_count == actionable + non_executable
    assert 0 <= summary.informational_target_count <= non_executable
    expected = (
        SemanticInventoryStatus.EMPTY
        if recognized == 0
        else SemanticInventoryStatus.REPRESENTED
        if omitted == 0
        else SemanticInventoryStatus.PARTIAL
    )
    assert summary.status is expected


@pytest.mark.parametrize(
    "kwargs",
    (
        {"status": SemanticInventoryStatus.EMPTY, "recognized_target_count": 1},
        {"status": SemanticInventoryStatus.REPRESENTED},
        {
            "status": SemanticInventoryStatus.REPRESENTED,
            "recognized_target_count": 1,
            "omitted_target_count": 1,
        },
        {
            "status": SemanticInventoryStatus.PARTIAL,
            "recognized_target_count": 1,
            "projected_target_count": 1,
            "non_executable_target_count": 1,
        },
        {
            "status": SemanticInventoryStatus.PARTIAL,
            "recognized_target_count": 1,
            "omitted_target_count": 1,
            "actionable_target_count": 1,
        },
        {
            "status": SemanticInventoryStatus.REPRESENTED,
            "recognized_target_count": 1,
            "projected_target_count": 1,
            "non_executable_target_count": 1,
            "informational_target_count": 2,
        },
    ),
)
def test_illegal_inventory_status_or_count_combinations_fail_closed(kwargs) -> None:
    with pytest.raises(ValueError):
        SemanticInventorySummary("fixture-profile.v1", **kwargs)


@pytest.mark.parametrize("value", (True, -1, MAX_SEMANTIC_INVENTORY_COUNT + 1, 1.5, None, "1"))
def test_inventory_counts_reject_bool_negative_overflow_and_wrong_types(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        SemanticInventorySummary(
            "fixture-profile.v1",
            SemanticInventoryStatus.REPRESENTED,
            value,  # type: ignore[arg-type]
            value,  # type: ignore[arg-type]
        )


def test_unassessed_is_the_only_zero_profile_neutral_default() -> None:
    summary = SemanticInventorySummary.unassessed()
    assert summary.status is SemanticInventoryStatus.UNASSESSED
    assert all(
        getattr(summary, field) == 0
        for field in (
            "recognized_target_count",
            "projected_target_count",
            "actionable_target_count",
            "non_executable_target_count",
            "omitted_target_count",
            "informational_target_count",
        )
    )


def test_surface_assessment_must_match_actual_targets_and_unique_binding_targets() -> None:
    target = SemanticTarget("target:one", "button", "One")
    binding = ActionBinding(
        "binding:one",
        "observation:one",
        "observation:one",
        "revision:one",
        "fingerprint:one",
        target.target_id,
        target.target_id,
        "fixture",
        "fixture",
        "activate",
        "click",
        "local_reversible",
        (),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {},
        risk=ActionRisk.LOW,
    )
    valid = SemanticInventorySummary.assessed(
        "fixture-profile.v1",
        recognized_target_count=1,
        projected_target_count=1,
        actionable_target_count=1,
        non_executable_target_count=0,
        omitted_target_count=0,
        informational_target_count=0,
    )
    source = SurfaceObservation(
        "observation:one",
        "fixture",
        "revision:one",
        ObservationSourceProfile.dom(),
        targets=(target,),
        bindings=(binding,),
        semantic_inventory=valid,
    )
    assert source.semantic_inventory is valid

    with pytest.raises(ValueError, match="projected targets"):
        SurfaceObservation(
            "observation:one",
            "fixture",
            "revision:one",
            ObservationSourceProfile.dom(),
            semantic_inventory=valid,
        )
    with pytest.raises(ValueError, match="binding targets"):
        SurfaceObservation(
            "observation:one",
            "fixture",
            "revision:one",
            ObservationSourceProfile.dom(),
            targets=(target,),
            semantic_inventory=valid,
        )


def test_untyped_inventory_status_fails_closed() -> None:
    with pytest.raises(TypeError):
        SemanticInventorySummary(
            "fixture-profile.v1",
            "empty",  # type: ignore[arg-type]
        )
