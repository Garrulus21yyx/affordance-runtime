from dataclasses import replace

from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)
from affordance_runtime.world.action_classification import EffectCategory

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _binding(action: str, category: str, effects: tuple[str, ...], risk: ActionRisk) -> ActionBinding:
    return ActionBinding(
        f"binding:{action}:{category}",
        "observation:1",
        "observation:1",
        "revision:1",
        f"fingerprint:{action}:{category}",
        "target:1",
        "target:1",
        "wot",
        "wot",
        action,
        "read_property" if action == "read" else "invoke_action",
        category,
        effects,
        SCHEMA,
        {},
        risk=risk,
    )


def _space(task: TaskGoal, bindings: tuple[ActionBinding, ...]):
    observation = WorldObservation(
        "observation:1",
        (SemanticTarget("target:1", "property", "Shared state"),),
        (),
        bindings,
        {"wot": CoverageState.COMPLETE},
    )
    return ActionSpaceBuilder().build(task, observation)


def test_effectful_task_can_observe_and_act_without_granting_read_effects() -> None:
    task = TaskGoal(
        "enable",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    read = _binding("read", EffectCategory.OBSERVATION, (), ActionRisk.LOW)
    effect = _binding("activate", EffectCategory.EXTERNAL, ("shared_state_enabled",), ActionRisk.HIGH)

    actions = {option.semantic_action for option in _space(task, (read, effect)).options}

    assert actions == {"read", "activate"}


def test_observation_action_must_be_low_risk_read_with_no_business_effect() -> None:
    task = TaskGoal(
        "enable",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    valid = _binding("read", EffectCategory.OBSERVATION, (), ActionRisk.LOW)
    invalid = (
        replace(valid, binding_id="binding:effect", semantic_effects=("shared_state_enabled",)),
        replace(valid, binding_id="binding:risk", risk=ActionRisk.HIGH),
        replace(valid, binding_id="binding:category", effect_category=EffectCategory.EXTERNAL),
    )

    assert len(_space(task, (valid, *invalid)).options) == 1


def test_read_only_task_still_excludes_business_effects() -> None:
    task = TaskGoal("inspect", "Inspect shared state")
    read = _binding("read", EffectCategory.OBSERVATION, (), ActionRisk.LOW)
    effect = _binding("activate", EffectCategory.EXTERNAL, ("shared_state_enabled",), ActionRisk.HIGH)

    options = _space(task, (read, effect)).options

    assert tuple(option.semantic_action for option in options) == ("read",)
