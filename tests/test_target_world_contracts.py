from dataclasses import fields

import pytest

from affordance_runtime.agent.decisions import Finish
from affordance_runtime.execution.contracts import ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.world import (
    ActionBinding,
    ActionSpaceBuilder,
    CoverageState,
    SemanticTarget,
    WorldObservation,
    build_agent_world_view,
)


def _world() -> WorldObservation:
    binding = ActionBinding(
        "binding-1",
        "obs-1",
        "share-toggle",
        "dom",
        "dom",
        ("click",),
        {"selector": "#shared", "credential": "never-policy-visible"},
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
    assert view.targets[0].supported_actions == ("click",)
    assert view.coverage["wot"] == CoverageState.NOT_ACQUIRED


def test_action_space_is_current_and_schema_is_immutable() -> None:
    space = ActionSpaceBuilder().build(_world())
    assert space.observation_id == "obs-1"
    assert space.options[0].observation_barrier is True
    assert space.options[0].batchable is False
    with pytest.raises(TypeError):
        space.options[0].parameter_schema["type"] = "array"  # type: ignore[index]


def test_policy_cannot_inject_execution_payload() -> None:
    option = ActionSpaceBuilder().build(_world()).options[0]
    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().validate_parameters(option, {"selector": "#other"})


def test_action_and_result_contracts_do_not_mix_binding_or_completion() -> None:
    assert "binding" not in {item.name for item in fields(ActionIntent)}
    assert "task_complete" not in {item.name for item in fields(ActionResult)}
    assert ActionResult("r1", DispatchStatus.SENT, "dom", True).transport_success
    assert isinstance(Finish({"suggested": True}), Finish)
