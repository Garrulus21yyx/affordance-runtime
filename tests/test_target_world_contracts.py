from dataclasses import fields

import pytest

from affordance_runtime.agent.decisions import Finish
from affordance_runtime.execution.contracts import ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinding,
    ActionSpaceBuilder,
    CoverageState,
    SemanticTarget,
    WorldObservation,
    build_agent_world_view,
)
from affordance_runtime.world.action_vocabulary import action_metadata


def _world() -> WorldObservation:
    binding = ActionBinding(
        binding_id="binding-1",
        world_observation_id="obs-1",
        source_observation_id="obs-1",
        source_revision="rev-1",
        target_fingerprint="fp-1",
        target_id="share-toggle",
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        semantic_effects=("shared_state_enabled",),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        payload={"selector": "#shared", "credential": "never-policy-visible"},
    )
    return WorldObservation(
        "obs-1",
        (SemanticTarget("share-toggle", "button", "Enable shared state", {"enabled": False}),),
        (),
        (binding,),
        {"dom": CoverageState.COMPLETE, "wot": CoverageState.NOT_ACQUIRED},
    )


def test_policy_view_hides_binding_payload_and_preserves_coverage_unknown() -> None:
    view = build_agent_world_view(_world())

    assert "selector" not in repr(view)
    assert "credential" not in repr(view)
    assert view.targets[0].supported_actions == ("activate",)
    assert view.coverage["wot"] == CoverageState.NOT_ACQUIRED


def test_action_space_is_current_and_schema_is_immutable() -> None:
    task = TaskGoal("share", "Enable sharing", ("local only",), ("shared_state_enabled",), risk_profile=RiskProfile.LOW)
    space = ActionSpaceBuilder().build(task, _world())
    assert space.observation_id == "obs-1"
    assert space.options[0].observation_barrier is True
    assert space.options[0].batchable is False
    with pytest.raises(TypeError):
        space.options[0].parameter_schema["type"] = "array"  # type: ignore[index]


def test_policy_cannot_inject_execution_payload() -> None:
    task = TaskGoal("share", "Enable sharing", allowed_effects=("shared_state_enabled",), risk_profile=RiskProfile.LOW)
    option = ActionSpaceBuilder().build(task, _world()).options[0]
    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().validate_parameters(option, {"selector": "#other"})


def test_action_and_result_contracts_do_not_mix_binding_or_completion() -> None:
    assert "binding" not in {item.name for item in fields(ActionIntent)}
    assert "task_complete" not in {item.name for item in fields(ActionResult)}
    assert ActionResult("r1", DispatchStatus.SENT, "dom", True).transport_success
    assert isinstance(Finish({"suggested": True}), Finish)


def test_surface_primitives_share_canonical_semantic_vocabulary() -> None:
    assert action_metadata("dom", "click").semantic_action == "activate"
    assert action_metadata("visual", "point_activate").semantic_action == "activate"
    assert action_metadata("wot", "invoke").semantic_action == "activate"


def test_task_forbidden_or_unallowed_effect_never_enters_action_space() -> None:
    forbidden = TaskGoal(
        "share",
        "Enable sharing",
        allowed_effects=("shared_state_enabled",),
        forbidden_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    unrelated = TaskGoal(
        "send",
        "Send message",
        allowed_effects=("message_sent",),
        risk_profile=RiskProfile.LOW,
    )

    assert ActionSpaceBuilder().build(forbidden, _world()).options == ()
    assert ActionSpaceBuilder().build(unrelated, _world()).options == ()


@pytest.mark.parametrize("value", [15, 31, "twenty"])
def test_parameter_schema_validates_type_and_range(value: object) -> None:
    option = ActionSpaceBuilder().build(
        TaskGoal("share", "Enable sharing", allowed_effects=("shared_state_enabled",), risk_profile=RiskProfile.LOW),
        _world(),
    ).options[0]
    ranged = type(option)(
        option.action_id,
        option.observation_id,
        "set_value",
        option.target_id,
        {
            "type": "object",
            "properties": {"value": {"type": "number", "minimum": 16, "maximum": 30}},
            "required": ["value"],
        },
        option.description,
        option.semantic_effects,
    )

    with pytest.raises(ValueError):
        ActionSpaceBuilder().validate_parameters(ranged, {"value": value})
