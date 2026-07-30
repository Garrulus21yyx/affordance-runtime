from __future__ import annotations

import pytest


def test_unified_observation_view_projects_planner_observation_without_mutable_snapshot() -> None:
    from affordance_runtime.planning_request import (
        PlannerAffordanceView,
        PlannerObservationView,
    )
    from affordance_runtime.unified_observation import UnifiedObservationView

    planner_observation = PlannerObservationView(
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
        observed_text="Name",
        affordances=(
            PlannerAffordanceView(
                target_id="semantic:name",
                surface="dom",
                role="textbox",
                label="Name",
                supported_actions=("type_text",),
                state={"value": ""},
                confidence=0.8,
                conflict_codes=("none",),
                source_refs=("source:control:1",),
            ),
        ),
        artifact_refs=("artifact:sha256:abc",),
    )

    unified = UnifiedObservationView.from_planner_observation(planner_observation)

    assert unified.snapshot_id == "snapshot-1"
    assert unified.targets[0].target_id == "semantic:name"
    assert unified.targets[0].supported_actions == ("type_text",)
    assert unified.targets[0].state["value"] == ""


def test_unified_observation_view_is_deeply_immutable() -> None:
    from affordance_runtime.planning_request import (
        PlannerAffordanceView,
        PlannerObservationView,
    )
    from affordance_runtime.unified_observation import UnifiedObservationView

    mutable_state = {"items": ["a"]}
    planner_observation = PlannerObservationView(
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
        observed_text="",
        affordances=(
            PlannerAffordanceView(
                target_id="semantic:list",
                surface="dom",
                role="listbox",
                label="Options",
                supported_actions=("select_option",),
                state=mutable_state,
            ),
        ),
        artifact_refs=(),
    )
    unified = UnifiedObservationView.from_planner_observation(planner_observation)

    mutable_state["items"].append("b")

    assert unified.targets[0].state["items"] == ("a",)
    with pytest.raises(TypeError):
        unified.targets[0].state["items"][0] = "b"  # type: ignore[index]


def test_unified_observation_rejects_duplicate_target_ids() -> None:
    from affordance_runtime.unified_observation import UnifiedObservationTarget, UnifiedObservationView

    target = UnifiedObservationTarget(
        target_id="semantic:name",
        surface="dom",
        role="textbox",
        label="Name",
        supported_actions=("type_text",),
        state={},
    )

    with pytest.raises(ValueError, match="unique"):
        UnifiedObservationView(
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
            observed_text="",
            targets=(target, target),
            artifact_refs=(),
        )
