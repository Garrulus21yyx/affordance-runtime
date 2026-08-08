from dataclasses import fields, replace

import pytest

from affordance_runtime.task import (
    EvaluationSpec,
    LocalObjective,
    LoopBudget,
    Milestone,
    RiskProfile,
    TaskGoal,
    TaskPlan,
)


def test_ordinary_read_goal_is_lightweight_and_deeply_immutable() -> None:
    goal = TaskGoal("read-title", "Read the title", inputs={"context": {"lang": "en"}})

    assert goal.risk_profile == RiskProfile.READ_ONLY
    with pytest.raises(TypeError):
        goal.inputs["context"]["lang"] = "de"  # type: ignore[index]


def test_effectful_goal_fails_closed_without_allowed_effects() -> None:
    with pytest.raises(ValueError, match="allowed_effects"):
        TaskGoal("enable", "Enable shared state", risk_profile=RiskProfile.LOW)


def test_task_goal_rejects_duplicate_computed_or_explicit_criterion_ids() -> None:
    duplicate = {"predicate": "ready", "value": True}
    with pytest.raises(ValueError, match="criterion IDs"):
        TaskGoal("task", "inspect", success_criteria=(duplicate, dict(duplicate)))

    with pytest.raises(ValueError, match="criterion IDs"):
        TaskGoal(
            "task",
            "inspect",
            success_criteria=(
                {"criterion_id": "same", "predicate": "first"},
                {"id": "same", "predicate": "second"},
            ),
        )


def test_task_goal_has_no_execution_or_planning_fields() -> None:
    names = {item.name for item in fields(TaskGoal)}
    assert not names.intersection({"page", "tab", "selector", "coordinate", "surface", "backend", "route", "plan"})


def test_strict_evaluation_does_not_add_effect_authority() -> None:
    spec = EvaluationSpec({"fact": "shared", "equals": True}, strict_source_lineage=True)
    goal = TaskGoal("read", "Inspect shared state", evaluation_spec=spec)

    assert goal.allowed_effects == ()


def test_optional_plan_can_be_bypassed_or_wholly_replaced() -> None:
    goal = TaskGoal("read", "Inspect state", loop_budget=LoopBudget(4, 8))
    first = TaskPlan("p1", (Milestone("m1", {"shared": True}),))
    second = replace(first, plan_id="p2", milestones=(Milestone("m2", {"verified": True}),))
    objective = LocalObjective({"shared": True})

    assert goal is not None
    assert first != second
    assert objective.desired_state == {"shared": True}
