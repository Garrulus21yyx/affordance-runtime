import hashlib
from dataclasses import replace

import pytest

from affordance_runtime.actions import (
    ActionBinding,
    ActionSpaceBuilder,
)
from affordance_runtime.surfaces.visual.grounding import VisualRegion
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    SemanticTarget,
    WorldObservation,
    build_agent_world_view,
)


def _visual_values():
    from affordance_runtime.surfaces.visual.contracts import (
        VisualFrame,
        VisualRegionBinding,
        VisualViewport,
    )

    viewport = VisualViewport(800, 600, 0.0, 0.0, 1.0, 1.0, "landscape-primary")
    screenshot_digest = "sha256:" + hashlib.sha256(b"png").hexdigest()
    frame = VisualFrame(
        "visual:obs-1",
        screenshot_digest,
        screenshot_digest,
        800,
        600,
        viewport,
        b"png",
    )
    region = VisualRegionBinding.from_region(
        frame,
        "M0",
        VisualRegion(
            (0.25, 0.25, 0.25, 0.2),
            "Enable shared state",
            0.95,
            normalized=True,
            role="button",
            primitive_action="point_activate",
            state={"enabled": False},
        ),
    )
    return viewport, frame, region


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observation_id", ""),
        ("screenshot_ref", ""),
        ("screenshot_digest", ""),
        ("image_width", 0),
        ("image_height", 0),
        ("image_bytes", b""),
    ],
)
def test_visual_frame_identity_fails_closed(field: str, value: object) -> None:
    _, frame, _ = _visual_values()

    with pytest.raises(ValueError):
        replace(frame, **{field: value})


@pytest.mark.parametrize("field", ["region_id", "region_fingerprint"])
def test_visual_region_identity_fails_closed(field: str) -> None:
    _, _, region = _visual_values()

    with pytest.raises(ValueError):
        replace(region, **{field: ""})


def test_visual_region_point_must_remain_inside_region() -> None:
    _, _, region = _visual_values()

    with pytest.raises(ValueError, match="inside"):
        replace(region, action_point_xy=(799.0, 599.0))


def test_visual_private_geometry_never_enters_policy_view() -> None:
    _, frame, region = _visual_values()
    target = SemanticTarget("visual:M0", region.role, region.label, dict(region.state))
    binding = ActionBinding(
        binding_id="visual-binding",
        world_observation_id=frame.observation_id,
        source_observation_id=frame.observation_id,
        source_revision=frame.source_revision,
        target_fingerprint=region.region_fingerprint,
        target_id=target.target_id,
        source_target_id=region.region_id,
        surface="visual",
        executor_id="visual",
        semantic_action="activate",
        primitive_action="point_activate",
        effect_category="local_reversible",
        semantic_effects=("shared_state_enabled",),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        payload=region.private_payload(),
    )
    world = WorldObservation(
        frame.observation_id,
        (target,),
        (),
        (binding,),
        {"visual": CoverageState.COMPLETE},
    )
    task = TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )

    view = build_agent_world_view(world)
    space = ActionSpaceBuilder().build(task, world)

    assert tuple(option.semantic_action for option in space.options) == ("activate",)
    policy_repr = repr((view, space))
    assert all(key not in policy_repr for key in ("bbox", "action_point", "viewport", "scroll", "zoom"))
    assert "point_activate" not in policy_repr
