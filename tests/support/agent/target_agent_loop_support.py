from affordance_runtime.agent import SelectAction
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
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
    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, recent_turns
        representation = repr(world)
        assert "selector" not in representation
        assert "action_point" not in representation
        return SelectAction(context.context_id, action_space.options[0].action_id)


class SharedStateTaskEvaluator:
    async def evaluate(self, task, observation):
        expanded = any(target.state.get("expanded") is True for target in observation.targets)
        fact_ref = next(fact.fact_id for fact in observation.facts if fact.predicate == "expanded")
        criteria = tuple(
            CriterionEvaluation(
                criterion_id(item),
                CriterionEvaluationStatus.SATISFIED
                if expanded
                else CriterionEvaluationStatus.UNSATISFIED,
                (fact_ref,),
                "shared state matches criterion" if expanded else "shared state does not match criterion",
            )
            for item in task.success_criteria
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if expanded else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if expanded else "shared state remains disabled",
            criteria,
            (fact_ref,) if expanded else (),
        )


class SharedStateActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        was_expanded = any(target.state.get("expanded") is True for target in before.targets)
        is_expanded = any(target.state.get("expanded") is True for target in after.targets)
        changed = not was_expanded and is_expanded
        coverage_complete = bool(after.source_manifest) and all(
            item.coverage == CoverageState.COMPLETE for item in after.source_manifest
        )
        if not changed and not coverage_complete:
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "fresh observation does not establish authoritative effect absence",
            )
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED
            if changed
            else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "shared state changed" if changed else "shared state did not change",
            (next(fact.fact_id for fact in after.facts if fact.predicate == "expanded"),),
        )


def run_immediate(coroutine):
    """Drive browser tests whose adapter coroutines intentionally do not yield."""

    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("real browser test unexpectedly yielded asynchronous work")
