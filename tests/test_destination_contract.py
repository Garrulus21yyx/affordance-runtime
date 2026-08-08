from dataclasses import replace

import pytest

from affordance_runtime.agent import SelectAction
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinder,
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpaceBuilder,
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


def test_destination_flows_from_policy_to_selection_intent_and_subject() -> None:
    option = _option()
    decision = SelectAction(option.action_id, {}, destination_id="person:alice")
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
        ),
        (),
        (binding,),
        {"dom": CoverageState.COMPLETE},
    )

    request = ActionBinder().bind(selection, observation)
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
    option = _option(eligible_destination_ids=(private_destination,))

    with pytest.raises(ValueError, match="runtime-private"):
        ActionSpaceBuilder().admit(option, {}, private_destination)
