from dataclasses import dataclass

from test_agent_loop import _world

from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionOption,
    ActionRelevancePolicy,
    ActionRelevanceRole,
    ActionSpaceBuilder,
)


@dataclass(frozen=True)
class _Objective:
    direct_target_ids: tuple[str, ...] = ()
    direct_effects: tuple[str, ...] = ()
    enabling_target_ids: tuple[str, ...] = ()
    enabling_action_hints: tuple[str, ...] = ()


def test_relevance_hint_classifies_without_changing_action_space_membership() -> None:
    task = TaskGoal(
        "enable",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    world = _world("obs:1", False)
    objective = _Objective(
        direct_target_ids=("shared-toggle",),
        direct_effects=("shared_state_enabled",),
    )
    without = ActionSpaceBuilder().build(task, world)
    with_objective = ActionSpaceBuilder().build(task, world)

    assert tuple(item.action_id for item in without.options) == tuple(item.action_id for item in with_objective.options)
    relevance = ActionRelevancePolicy().classify(with_objective.options[0], objective)
    assert relevance.role == ActionRelevanceRole.DIRECT


def test_relevance_roles_are_deterministic_from_explicit_semantics_only() -> None:
    task = TaskGoal(
        "enable",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    option = ActionSpaceBuilder().build(task, _world("obs:1", False)).options[0]
    policy = ActionRelevancePolicy()

    enabling = policy.classify(
        option,
        _Objective(enabling_action_hints=("activate",)),
    )
    other = policy.classify(option, _Objective())

    assert enabling.role == ActionRelevanceRole.ENABLING
    assert other.role == ActionRelevanceRole.OTHER
    assert "label" not in enabling.reason_codes


def test_explicit_direct_hint_takes_precedence_for_read_action() -> None:
    option = ActionOption(
        "action:read",
        "obs:1",
        "read",
        "target:read",
        "observation",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        ("binding:1",),
        "read state",
    )
    objective = _Objective(direct_target_ids=("target:read",))

    relevance = ActionRelevancePolicy().classify(option, objective)

    assert relevance.role == ActionRelevanceRole.DIRECT
    assert "explicit_direct_target" in relevance.reason_codes


def test_registered_interaction_action_is_enabling_without_business_effect() -> None:
    option = ActionOption(
        "action:reveal",
        "obs:1",
        "activate",
        "target:reveal",
        "interaction",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        ("binding:1",),
        "reveal details",
    )

    relevance = ActionRelevancePolicy().classify(option, None)

    assert relevance.role == ActionRelevanceRole.ENABLING
    assert relevance.reason_codes == ("interaction_action",)
