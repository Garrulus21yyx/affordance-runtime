from dataclasses import replace

import pytest

from affordance_runtime.actions import (
    ActionBinder,
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpaceBuilder,
    AdmittedActionSelection,
)
from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionIntent, BoundActionRequest
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    SemanticTarget,
)
from tests.support.action_contracts import verification_kwargs
from tests.support.world import fused_world

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _option(**changes) -> ActionOption:
    option = ActionOption(
        "action:send",
        "observation:1",
        "drag_to",
        "message:quarterly",
        "external",
        SCHEMA,
        schema_digest(SCHEMA),
        ("binding:send",),
        "Send message",
        ("message_sent",),
        ActionRisk.HIGH,
        destination_required=True,
        eligible_destination_ids=("person:alice", "person:bob"),
        **verification_kwargs("drag_to", schema_digest(SCHEMA), ("message_sent",)),
    )
    return replace(option, **changes)


def _task() -> TaskGoal:
    return TaskGoal(
        "send",
        "Send the quarterly report",
        allowed_effects=("message_sent",),
        risk_profile=RiskProfile.HIGH,
    )


def _destination_binding(binding_id: str, destinations: tuple[str, ...]) -> ActionBinding:
    return ActionBinding(
        binding_id,
        "observation:1",
        "observation:1",
        "revision:1",
        f"fingerprint:{binding_id}",
        "message:quarterly",
        "message:quarterly",
        "dom",
        "dom",
        "drag_to",
        "drag",
        "external",
        ("message_sent",),
        SCHEMA,
        {"selector": f"#{binding_id}"},
        risk=ActionRisk.HIGH,
        destination_required=True,
        eligible_destination_ids=destinations,
    )


def _destination_world(*bindings: ActionBinding):
    return fused_world(
        "observation:1",
        (
            SemanticTarget("message:quarterly", "message", "Quarterly report"),
            SemanticTarget("person:alice", "person", "Alice"),
            SemanticTarget("person:bob", "person", "Bob"),
            SemanticTarget("person:carol", "person", "Carol"),
        ),
        bindings=bindings,
        surface="dom",
    )


def test_partially_overlapping_destination_contracts_fail_closed_on_atomic_route() -> None:
    left = _destination_binding("binding:left", ("person:alice", "person:bob"))
    right = replace(
        _destination_binding("binding:right", ("person:bob", "person:carol")),
        observation_barrier=False,
        **verification_kwargs(
            "drag_to",
            schema_digest(SCHEMA),
            ("message_sent",),
            observation_barrier=False,
        ),
    )

    space = ActionSpaceBuilder().build(_task(), _destination_world(left, right))

    assert tuple(option.eligible_destination_ids for option in space.options) == (
        ("person:alice",),
        ("person:carol",),
    )
    assert len(space.issues) == 1
    assert space.issues[0].code.value == "action_route_conflict"
    assert space.issues[0].destination_ids == ("person:bob",)
    assert space.issues[0].conflicting_contract_fields == (
        "observation_barrier",
        "verification_contract",
    )

    world = _destination_world(left, right)
    context = ContextBuilder().build(
        _task(),
        world,
        space,
        TaskEvaluation(
            _task().task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "route conflict why-not witness",
        ),
    )
    counts = {item.kind.value: 0 for item in context.action_delivery_plan.obligations}
    counts["issues"] = 1
    delivery = build_model_turn_delivery(context, include_images=False, admitted_records=counts)
    assert "ActionRouteIssues" in delivery.view.text
    assert "code=action_route_conflict operation=drag_to" in delivery.view.text
    assert "observation_barrier" in delivery.view.text
    assert all(
        route.destination_ref != context.grounding.target_refs["person:bob"]
        for route in delivery.manifest.action_routes
    )


def test_compatible_destination_adjacency_merges_without_cartesian_route_loss() -> None:
    left = _destination_binding("binding:left", ("person:alice", "person:bob"))
    right = _destination_binding("binding:right", ("person:bob", "person:carol"))
    world = _destination_world(left, right)

    space = ActionSpaceBuilder().build(_task(), world)

    assert space.issues == ()
    assert len(space.options) == 1
    option = space.options[0]
    assert option.eligible_destination_ids == (
        "person:alice",
        "person:bob",
        "person:carol",
    )
    assert option.eligible_binding_ids == ("binding:left", "binding:right")
    admitted = ActionSpaceBuilder().admit(option, {}, "person:carol")
    bound = ActionBinder().bind(admitted, world, "context:test")
    assert bound.binding.binding_id == "binding:right"


def test_destination_admission_requires_one_current_offered_semantic_id() -> None:
    builder = ActionSpaceBuilder()

    with pytest.raises(ValueError, match="destination is required"):
        builder.admit(_option(), {}, "")
    with pytest.raises(ValueError, match="not offered"):
        builder.admit(_option(), {}, "person:mallory")
    forbidden = replace(
        _option(),
        semantic_action="activate",
        destination_required=False,
        eligible_destination_ids=(),
        semantic_effects=(),
        **verification_kwargs("activate", schema_digest(SCHEMA), ()),
    )
    with pytest.raises(ValueError, match="does not accept"):
        builder.admit(forbidden, {}, "person:alice")


def test_nested_runtime_private_parameter_is_rejected() -> None:
    option = _option()
    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().admit(option, {"href": "/private"}, "person:alice")


@pytest.mark.parametrize(
    "schema",
    (
        {"type": "object", "properties": {}, "required": ["selector"], "additionalProperties": False},
        {"type": "object", "properties": {"name": {"type": "array"}}, "additionalProperties": False},
        {"type": "array"},
    ),
)
def test_parameter_schema_contract_fails_closed_at_option_construction(schema) -> None:
    with pytest.raises(ValueError):
        _option(parameter_schema=schema, schema_digest="schema:invalid")


def test_destination_flows_from_policy_to_selection_intent_and_subject() -> None:
    option = _option()
    decision = SelectAction("context:test", option.action_id, {}, destination_id="person:alice")
    selection = ActionSpaceBuilder().admit(option, dict(decision.parameters), decision.destination_id)
    binding = ActionBinding(
        "binding:send",
        "observation:1",
        "observation:1",
        "revision:1",
        "fingerprint:send",
        "message:quarterly",
        "message:quarterly",
        "dom",
        "dom",
        "drag_to",
        "drag",
        "external",
        ("message_sent",),
        SCHEMA,
        {"selector": "#send"},
        risk=ActionRisk.HIGH,
        destination_required=True,
        eligible_destination_ids=("person:alice", "person:bob"),
    )
    observation = fused_world(
        "observation:1",
        (
            SemanticTarget("message:quarterly", "message", "Quarterly report"),
            SemanticTarget("person:alice", "person", "Alice"),
            SemanticTarget("person:bob", "person", "Bob"),
        ),
        bindings=(binding,),
        surface="dom",
    )

    request = ActionBinder().bind(selection, observation, "context:test")
    assessment = RiskPolicy().assess(_task(), selection)
    bob = replace(selection, destination_id="person:bob")

    assert selection.destination_id == "person:alice"
    assert request.intent.destination_id == "person:alice"
    assert assessment.subject_id != RiskPolicy().assess(_task(), bob).subject_id


@pytest.mark.parametrize(
    "private_destination",
    ("selector:#alice", "coordinate:10,20", "https://private.example/alice", "href:/alice"),
)
def test_destination_private_route_injection_is_rejected(private_destination: str) -> None:
    with pytest.raises(ValueError, match="runtime-private"):
        _option(eligible_destination_ids=(private_destination,))


@pytest.mark.parametrize(
    "destinations",
    (("",), ("person:alice", "person:alice"), ("href:/alice",)),
)
def test_destination_ids_fail_closed_in_direct_binding_and_option_construction(destinations) -> None:
    with pytest.raises(ValueError, match="destination"):
        _option(eligible_destination_ids=destinations)
    with pytest.raises(ValueError, match="destination"):
        ActionBinding(
            "binding:send",
            "observation:1",
            "observation:1",
            "revision:1",
            "fingerprint:send",
            "message:quarterly",
            "message:quarterly",
            "dom",
            "dom",
            "drag_to",
            "drag",
            "external",
            ("message_sent",),
            SCHEMA,
            {},
            destination_required=True,
            eligible_destination_ids=destinations,
        )


def test_direct_selection_and_request_revalidate_destination_membership() -> None:
    values = dict(
        action_id="action:send",
        observation_id="observation:1",
        semantic_action="drag_to",
        target_id="message:quarterly",
        effect_category="external",
        semantic_effects=("message_sent",),
        schema_digest=schema_digest(SCHEMA),
        eligible_binding_ids=("binding:send",),
        risk=ActionRisk.HIGH,
        observation_barrier=True,
        destination_required=True,
        eligible_destination_ids=("person:alice",),
        **verification_kwargs("drag_to", schema_digest(SCHEMA), ("message_sent",)),
    )
    with pytest.raises(ValueError, match="destination is required"):
        AdmittedActionSelection(**values)
    with pytest.raises(ValueError, match="not offered"):
        AdmittedActionSelection(**values, destination_id="person:bob")

    selection = AdmittedActionSelection(**values, destination_id="person:alice")
    binding = ActionBinding(
        "binding:send",
        "observation:1",
        "observation:1",
        "revision:1",
        "fingerprint:send",
        "message:quarterly",
        "message:quarterly",
        "dom",
        "dom",
        "drag_to",
        "drag",
        "external",
        ("message_sent",),
        SCHEMA,
        {},
        risk=ActionRisk.HIGH,
        destination_required=True,
        eligible_destination_ids=("person:alice",),
    )
    with pytest.raises(ValueError, match="admitted option"):
        BoundActionRequest(
            "request:1",
            "context:test",
            "observation:1",
            ActionIntent("drag_to", "message:quarterly", destination_id="person:bob"),
            selection,
            binding,
        )


def test_world_observation_requires_destination_targets_in_current_world() -> None:
    binding = ActionBinding(
        "binding:send",
        "observation:1",
        "observation:1",
        "revision:1",
        "fingerprint:send",
        "message:quarterly",
        "message:quarterly",
        "dom",
        "dom",
        "drag_to",
        "drag",
        "external",
        ("message_sent",),
        SCHEMA,
        {},
        destination_required=True,
        eligible_destination_ids=("person:alice",),
    )
    with pytest.raises(ValueError, match="unresolved_source_binding"):
        fused_world(
            "observation:1",
            (SemanticTarget("message:quarterly", "message", "Quarterly report"),),
            bindings=(binding,),
            surface="dom",
        )
