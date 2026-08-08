from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

from affordance_runtime.agent.decisions import Finish
from affordance_runtime.execution.contracts import (
    ActionIntent,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinder,
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    CoverageState,
    SemanticTarget,
    WorldObservation,
    build_agent_world_view,
)
from affordance_runtime.world.action_classification import classify_dom_action
from affordance_runtime.world.action_vocabulary import action_metadata


def _world() -> WorldObservation:
    binding = ActionBinding(
        binding_id="binding-1",
        world_observation_id="obs-1",
        source_observation_id="obs-1",
        source_revision="rev-1",
        target_fingerprint="fp-1",
        target_id="share-toggle",
        source_target_id="share-toggle",
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        effect_category="local_reversible",
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


@pytest.mark.parametrize("private_key", ["x", "y", "bbox", "coordinate", "backend", "selector", "point"])
def test_policy_cannot_inject_execution_payload(private_key: str) -> None:
    task = TaskGoal("share", "Enable sharing", allowed_effects=("shared_state_enabled",), risk_profile=RiskProfile.LOW)
    option = ActionSpaceBuilder().build(task, _world()).options[0]
    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().validate_parameters(option, {private_key: "injected"})


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
        option.effect_category,
        {
            "type": "object",
            "properties": {"value": {"type": "number", "minimum": 16, "maximum": 30}},
            "required": ["value"],
        },
        option.schema_digest,
        option.eligible_binding_ids,
        option.description,
        option.semantic_effects,
    )

    with pytest.raises(ValueError):
        ActionSpaceBuilder().validate_parameters(ranged, {"value": value})


def test_selected_option_only_binds_its_exact_allowed_group() -> None:
    allowed = replace(_world().bindings[0], binding_id="allowed", confidence=0.5)
    forbidden = replace(
        allowed,
        binding_id="forbidden",
        semantic_effects=("message_sent",),
        confidence=0.99,
    )
    world = replace(_world(), bindings=(allowed, forbidden))
    task = TaskGoal(
        "share",
        "Enable sharing",
        allowed_effects=("shared_state_enabled",),
        forbidden_effects=("message_sent",),
        risk_profile=RiskProfile.LOW,
    )
    builder = ActionSpaceBuilder()
    option = builder.build(task, world).options[0]

    request = ActionBinder().bind(builder.admit(option, {}), world)

    assert option.eligible_binding_ids == ("allowed",)
    assert request.binding.binding_id == "allowed"


def test_schema_variants_have_distinct_option_identity_and_routes() -> None:
    first = replace(
        _world().bindings[0],
        binding_id="string-route",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    second = replace(
        first,
        binding_id="number-route",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
        },
    )
    world = replace(_world(), bindings=(first, second))
    task = TaskGoal("share", "Enable sharing", allowed_effects=("shared_state_enabled",), risk_profile=RiskProfile.LOW)
    builder = ActionSpaceBuilder()
    options = builder.build(task, world).options

    assert len(options) == 2
    assert len({option.action_id for option in options}) == 2
    for option in options:
        value = 1 if option.parameter_schema["properties"]["value"]["type"] == "number" else "one"
        request = ActionBinder().bind(builder.admit(option, {"value": value}), world)
        assert request.binding.binding_id == option.eligible_binding_ids[0]


def test_unsupported_schema_type_fails_closed() -> None:
    option = ActionSpaceBuilder().build(
        TaskGoal("share", "Enable sharing", allowed_effects=("shared_state_enabled",), risk_profile=RiskProfile.LOW),
        _world(),
    ).options[0]
    unsupported = replace(
        option,
        parameter_schema={"type": "object", "properties": {"items": {"type": "array"}}},
    )

    with pytest.raises(ValueError, match="unsupported schema type"):
        ActionSpaceBuilder().validate_parameters(unsupported, {"items": []})


def test_page_metadata_cannot_grant_effect_or_lower_runtime_risk() -> None:
    task = TaskGoal("safe", "Perform safe update", allowed_effects=("safe_update",), risk_profile=RiskProfile.LOW)
    claimed = SimpleNamespace(
        role="link",
        externality="external_system",
        reversibility="reversible",
        operation_ref="external.commit@v1",
        effect_class="ungranted_effect",
        risk=SimpleNamespace(value="low"),
        risk_asserted=True,
    )

    classification = classify_dom_action(task, claimed, "activate")

    assert classification.semantic_effects == ("safe_update",)
    assert classification.risk == ActionRisk.HIGH


@pytest.mark.parametrize(
    "mutation",
    [
        "semantic_action",
        "target_id",
        "parameters",
        "schema_digest",
        "higher_risk",
        "observation_barrier",
    ],
)
def test_bound_request_rejects_mismatched_selection_invariants(mutation: str) -> None:
    world = _world()
    task = TaskGoal(
        "share",
        "Enable sharing",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    builder = ActionSpaceBuilder()
    option = builder.build(task, world).options[0]
    selection = builder.admit(option, {})
    intent = ActionIntent(selection.semantic_action, selection.target_id, dict(selection.parameters))
    binding = world.bindings[0]
    if mutation == "semantic_action":
        intent = replace(intent, semantic_action="read")
    elif mutation == "target_id":
        intent = replace(intent, target_id="other-target")
    elif mutation == "parameters":
        intent = replace(intent, parameters={"unexpected": True})
    elif mutation == "schema_digest":
        selection = replace(selection, schema_digest="sha256:wrong")
    elif mutation == "higher_risk":
        binding = replace(binding, risk=ActionRisk.MEDIUM)
    elif mutation == "observation_barrier":
        binding = replace(binding, observation_barrier=False)

    with pytest.raises(ValueError, match="bound request"):
        BoundActionRequest("request-1", world.observation_id, intent, selection, binding)
