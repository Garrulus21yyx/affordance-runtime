from test_agent_loop import _world

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.task.frontier_contracts import ActiveObjective, TaskOutcomeIs, TaskOutcomeStatus


def test_objective_mutators_increment_progress_revision() -> None:
    state = AgentLoopState(_world("before", False))
    objective = ActiveObjective(
        "objective:1",
        ("criterion:1",),
        TaskOutcomeIs(TaskOutcomeStatus.COMPLETE),
        "context:1",
    )

    state.set_active_objective(objective)
    state.clear_active_objective()

    assert state.active_objective is None
    assert state.progress_revision == 2


def test_pending_mutators_increment_pending_revision() -> None:
    state = AgentLoopState(_world("before", False))

    state.set_pending_question("question")
    state.clear_pending_question()

    assert state.pending_user_question == ""
    assert state.pending_revision == 2
