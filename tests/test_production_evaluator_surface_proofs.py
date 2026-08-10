import asyncio

import pytest
from target_agent_loop_support import run_immediate, shared_state_task
from test_surface_symmetry_matrix import profile_environment

from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder


@pytest.mark.parametrize("profile", ["dom", "visual", "wot"])
def test_three_surfaces_share_mechanical_runtime_composition(profile: str) -> None:
    async def scenario(environment):
        task = shared_state_task()
        evaluator = ProductionTaskEvaluator()
        acquisition = await environment.reset(task)
        assert acquisition.observation is not None
        before = acquisition.observation
        action_space = ActionSpaceBuilder().build(task, before)
        assert len(action_space.options) == 1
        selection = ActionSpaceBuilder().admit(action_space.options[0], {})
        request = ActionBinder().bind(selection, before, "context:mechanical-proof")
        outcome = await environment.execute(request)
        execution = outcome.result
        after = outcome.post_acquisition.observation
        assert after is not None
        task_evaluation = await evaluator.evaluate(task, after)
        return before, execution, after, task_evaluation

    with profile_environment(profile) as (environment, metrics):
        before, execution, after, evaluation = run_immediate(scenario(environment))

    assert before.observation_id != after.observation_id
    assert execution.transport_success is True
    assert metrics["actions"]() == 1
    assert evaluation.status == TaskEvaluationStatus.COMPLETE
    assert len(evaluation.criteria) == 1
    assert evaluation.criteria[0].evidence_refs


def test_mechanical_composition_never_needs_an_event_loop_side_channel() -> None:
    """The production evaluator itself is an ordinary one-shot async protocol."""

    assert asyncio.iscoroutinefunction(ProductionTaskEvaluator.evaluate)
