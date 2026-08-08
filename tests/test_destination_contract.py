from dataclasses import replace

import pytest

from affordance_runtime.agent import SelectAction
from affordance_runtime.execution import ActionIntent, BoundActionRequest
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinder,
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpaceBuilder,
    AdmittedActionSelection,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _option(**changes) -> ActionOption:
    option = ActionOption(
        "action:send",
        "observation:1",
        "send",
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
    )
    return replace(option, **changes)


def _task() -> TaskGoal:
    return TaskGoal(
        "send",
        "Send the quarterly report",
        allowed_effects=("message_sent",),
        risk_profile=RiskProfile.HIGH,
    )


def test_destination_admission_requires_one_current_offered_semantic_id() -> None:
    builder = ActionSpaceBuilder()

    with pytest.raises(ValueError, match="destination is required"):
        builder.admit(_option(), {}, "")
    with pytest.raises(ValueError, match="not offered"):
        builder.admit(_option(), {}, "person:mallory")
    with pytest.raises(ValueError, match="does not accept"):
        builder.admit(
            _option(destination_required=False, eligible_destination_ids=()),
            {},
            "person:alice",
        )


def test_nested_runtime_private_parameter_is_rejected() -> None:
    schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "object",
                "properties": {"body": {"type": "string"}},
                "additionalProperties": True,
            }
        },
        "additionalProperties": False,
    }
    option = _option(parameter_schema=schema, schema_digest=schema_digest(schema))

    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().admit(option, {"message": {"body": "ok", "href": "/private"}}, "person:alice")


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
        "send",
        "click",
        "external",
        ("message_sent",),
        SCHEMA,
        {"selector": "#send"},
        risk=ActionRisk.HIGH,
        destination_required=True,
        eligible_destination_ids=("person:alice", "person:bob"),
    )
    observation = WorldObservation(
        "observation:1",
        (
            SemanticTarget("message:quarterly", "message", "Quarterly report"),
            SemanticTarget("person:alice", "person", "Alice"),
            SemanticTarget("person:bob", "person", "Bob"),
        ),
        (),
        (binding,),
        {"dom": CoverageState.COMPLETE},
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
            "send",
            "click",
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
        semantic_action="send",
        target_id="message:quarterly",
        effect_category="external",
        semantic_effects=("message_sent",),
        schema_digest=schema_digest(SCHEMA),
        eligible_binding_ids=("binding:send",),
        risk=ActionRisk.HIGH,
        observation_barrier=True,
        destination_required=True,
        eligible_destination_ids=("person:alice",),
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
        "send",
        "click",
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
            ActionIntent("send", "message:quarterly", destination_id="person:bob"),
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
        "send",
        "click",
        "external",
        ("message_sent",),
        SCHEMA,
        {},
        destination_required=True,
        eligible_destination_ids=("person:alice",),
    )
    with pytest.raises(ValueError, match="destination target"):
        WorldObservation(
            "observation:1",
            (SemanticTarget("message:quarterly", "message", "Quarterly report"),),
            (),
            (binding,),
            {"dom": CoverageState.COMPLETE},
        )
