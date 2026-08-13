from dataclasses import fields

import pytest

from affordance_runtime.task import (
    EvaluationSpec,
    LocalObjective,
    LoopBudget,
    RiskProfile,
    TaskGoal,
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


def test_local_objective_remains_separate_from_task_intake() -> None:
    goal = TaskGoal("read", "Inspect state", loop_budget=LoopBudget(4, 8))
    objective = LocalObjective({"shared": True})

    assert goal is not None
    assert objective.desired_state == {"shared": True}
