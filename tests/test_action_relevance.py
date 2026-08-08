from test_agent_loop import _world

from affordance_runtime.task import LocalObjective, RiskProfile, TaskGoal
from affordance_runtime.world import ActionRelevancePolicy, ActionRelevanceRole, ActionSpaceBuilder


def test_local_objective_classifies_without_changing_action_space_membership() -> None:
    task = TaskGoal(
        "enable",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    world = _world("obs:1", False)
    objective = LocalObjective(
        {"enabled": True},
        direct_target_ids=("shared-toggle",),
        direct_effects=("shared_state_enabled",),
    )
    without = ActionSpaceBuilder().build(task, world)
    with_objective = ActionSpaceBuilder().build(task, world, objective)

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
        LocalObjective({"enabled": True}, enabling_action_hints=("activate",)),
    )
    other = policy.classify(option, LocalObjective({"enabled": True}))

    assert enabling.role == ActionRelevanceRole.ENABLING
    assert other.role == ActionRelevanceRole.OTHER
    assert "label" not in enabling.reason_codes
