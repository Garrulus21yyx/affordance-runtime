from affordance_runtime.agent.state import AgentLoopState
from tests.integration.agent.test_agent_loop import _world


def test_pending_mutators_increment_pending_revision() -> None:
    state = AgentLoopState(_world("before", False))

    state.set_pending_question("question")
    state.clear_pending_question()

    assert state.pending_user_question == ""
    assert state.pending_revision == 2
