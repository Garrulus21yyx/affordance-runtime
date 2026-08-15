from __future__ import annotations

import asyncio
import json

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent import AgentLoop, AgentLoopStatus, AskUser
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.transition_digest_projection import project_latest_transition
from affordance_runtime.agent.control_outcome import Pause
from affordance_runtime.agent.control_reducer import (
    ApplyUserInputContinuation,
    ControlAccepted,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.control_transition import ControlTransitionScope
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.agent.user_input import UserInputContinuation
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.model.policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import _build_request
from tests.integration.agent.test_agent_loop import (
    ScriptedPolicy,
    SharedActionEvaluator,
    SharedTaskEvaluator,
    _sent,
    _task,
    _world,
)


def test_context_projects_exact_action_root_once() -> None:
    async def scenario():
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=[_sent()],
        )
        loop = AgentLoop(ScriptedPolicy(["first"]), SharedActionEvaluator(), SharedTaskEvaluator())
        return await loop.run(environment, _task())

    result = asyncio.run(scenario())
    transition = result.control_transitions[-1]
    state = AgentLoopState(
        result.final_observation,
        recent_control_transitions=result.control_transitions,
        control_transition_total_count=result.control_transition_total_count,
        current_task_evaluation=transition.task_evaluation,
    )
    action_space = ActionSpaceBuilder().build(_task(), result.final_observation)
    context = ContextBuilder().build(_task(), state, action_space, transition.task_evaluation)

    digest = context.last_transition
    assert digest is not None
    assert digest.transition_id == transition.transition_id
    assert digest.lineage.before_observation_id == "before"
    assert digest.lineage.after_observation_id == "after"
    assert digest.execution_outcome.dispatch_status == "sent"
    assert digest.effect_assessment.status == "effect_confirmed"

    catalog = compile_grounded_action_catalog(context)
    messages = GroundedPolicyContextBinder().action_messages(
        context,
        catalog.specs,
        _build_request(context),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        include_tool_menu=True,
    )
    assert isinstance(messages[1].content, str)
    public = json.loads(messages[1].content)
    assert "last_transition" not in public
    assert len(public["recent_steps"]) == 1
    assert public["recent_steps"][0]["action"]["tool"] == "activate"
    assert public["recent_steps"][0]["result"]["effect"] == "effect_confirmed"


def test_user_input_continuation_replaces_same_exact_root_once() -> None:
    world = _world("observation:1", False)
    loop_state = AgentLoopState(world)
    scope = ControlTransitionScope(
        loop_state,
        AskUser("context:one", "Which value?", ("value",)),
    )
    loop_state.set_pending_question("Which value?")
    scope.set_reason("user_input_requested")
    root = scope.finalize(
        loop_state,
        Pause(AgentLoopStatus.WAITING_USER, "user_input_requested", "Which value?"),
    )
    control = ControlState((root,), 1, (("AskUser", 1),))
    continuation = UserInputContinuation(
        "user-input:0123456789abcdef01234567",
        root.transition_id,
        "task",
        1,
        2,
    )

    accepted = reduce_control(control, ApplyUserInputContinuation(continuation))
    assert isinstance(accepted, ControlAccepted)
    assert accepted.state.total_count == 1
    assert accepted.state.recent_transitions[0].transition_id == root.transition_id


def test_projection_is_bounded_and_cannot_reconstruct_authority() -> None:
    world = _world("observation:1", False)
    state = AgentLoopState(world)
    scope = ControlTransitionScope(state, AskUser("context:one", "Value?", ("value",)))
    state.set_pending_question("Value?")
    scope.set_reason("user_input_requested")
    transition = scope.finalize(
        state,
        Pause(AgentLoopStatus.WAITING_USER, "user_input_requested", "Value?"),
    )
    digest = project_latest_transition(
        (transition,),
        AgentGroundingIndexView(),
        max_progress_changes=1,
        max_evidence_refs=1,
    )
    assert digest is not None
    assert not hasattr(digest, "before_observation")
    assert not hasattr(digest, "execution")
