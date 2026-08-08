from affordance_runtime.agent import SelectAction
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import CoverageState


def shared_state_task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )


class FirstOfferedActionPolicy:
    async def decide(self, task, world, action_space, recent_turns, optional_plan):
        del task, recent_turns, optional_plan
        representation = repr(world)
        assert "selector" not in representation
        assert "action_point" not in representation
        return SelectAction(action_space.options[0].action_id)


class SharedStateTaskEvaluator:
    async def evaluate(self, task, observation):
        del task
        expanded = any(target.state.get("expanded") is True for target in observation.targets)
        return TaskEvaluation(
            TaskEvaluationStatus.COMPLETE if expanded else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if expanded else "shared state remains disabled",
        )


class SharedStateActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, request, result
        was_expanded = any(target.state.get("expanded") is True for target in before.targets)
        is_expanded = any(target.state.get("expanded") is True for target in after.targets)
        changed = not was_expanded and is_expanded
        coverage_complete = bool(after.coverage) and all(
            item == CoverageState.COMPLETE for item in after.coverage.values()
        )
        if not changed and not coverage_complete:
            return ActionEvaluation(
                ActionEvaluationStatus.UNKNOWN,
                "fresh observation does not establish authoritative effect absence",
            )
        return ActionEvaluation(
            ActionEvaluationStatus.EFFECT_CONFIRMED
            if changed
            else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "shared state changed" if changed else "shared state did not change",
        )


def run_immediate(coroutine):
    """Drive browser tests whose adapter coroutines intentionally do not yield."""

    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("real browser test unexpectedly yielded asynchronous work")
