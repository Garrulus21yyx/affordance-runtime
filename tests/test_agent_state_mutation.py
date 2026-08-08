from test_agent_loop import _world

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.task import LocalObjective, Milestone, TaskPlan


def test_objective_and_plan_mutators_increment_progress_revision() -> None:
    state = AgentLoopState(_world("before", False))
    objective = LocalObjective({"enabled": True})
    plan = TaskPlan("plan:1", (Milestone("m:1", {"enabled": True}),))

    state.set_active_objective(objective)
    state.clear_active_objective()
    state.replace_plan(plan)

    assert state.active_objective is None
    assert state.plan == plan
    assert state.progress_revision == 3


def test_pending_mutators_increment_pending_revision() -> None:
    state = AgentLoopState(_world("before", False))

    state.set_pending_question("question")
    state.clear_pending_question()

    assert state.pending_user_question == ""
    assert state.pending_revision == 2
