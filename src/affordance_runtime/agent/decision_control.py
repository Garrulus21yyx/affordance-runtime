"""One-shot typed decision admission and surface-neutral routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.observation_control import FreshObservationUnavailable, observe_fresh
from affordance_runtime.agent.policy import AgentPolicy, TaskEvaluator
from affordance_runtime.agent.result import build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus, Turn
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.agent.waiting import WaitController
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.world.action_paging import ActionPager
from affordance_runtime.world.contracts import ActionSpace

SelectionExecutor = Callable[[AgentRunSession, ActionSpace, SelectAction], Awaitable[object]]


def accept_current_decision(session: AgentRunSession, decision: AgentDecision) -> bool:
    context = session.current_context_snapshot
    if context is None or decision.context_id != context.context_id:
        return False
    if session.consumed_context_id == context.context_id:
        return False
    session.consumed_context_id = context.context_id
    return True


async def run_policy_turn(
    session: AgentRunSession,
    action_space: ActionSpace,
    task_evaluation: TaskEvaluation,
    policy: AgentPolicy,
    context_builder: ContextBuilder,
    task_evaluator: TaskEvaluator,
    waiter: WaitController,
    execute_selection: SelectionExecutor,
) -> object:
    task, state = session.task, session.state
    context = context_builder.build(
        task,
        state,
        action_space,
        task_evaluation,
        session.intent_context,
        session.current_action_page,
        observation_count=session.observation_count,
        context_generation=session.next_context_generation(),
    )
    session.current_context_snapshot = context
    decision = await policy.decide(context)
    state.remaining_turns -= 1
    if not accept_current_decision(session, decision):
        return None
    if isinstance(decision, AskUser):
        state.set_pending_question(decision.question)
        return build_result(AgentLoopStatus.WAITING_USER, task, state, 0, 0, decision.question)
    if isinstance(decision, Abort):
        return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, decision.reason)
    if isinstance(decision, ProposeDone):
        return await _propose_done(session, decision, task_evaluator)
    if isinstance(decision, RequestObservation):
        capabilities = {(item.modality, item.assurance) for item in context.world.observation_capabilities}
        if (decision.modality, decision.required_assurance) not in capabilities:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "observation capability was not offered")
        return await _fresh_observation(session, decision, decision.reason)
    if isinstance(decision, Wait):
        if not _can_observe(session):
            return observation_budget_result(task, state, 0, 0)
        await waiter.wait(decision.max_wait_ms)
        return await _fresh_observation(session, decision, "fresh observation after wait")
    if isinstance(decision, RequestActionPage):
        labels = {item.target_id: item.label for item in state.current_observation.targets}
        try:
            session.current_action_page = context_builder.pager.page(
                action_space,
                state.active_objective,
                query=decision.query,
                target_id=decision.target_id,
                relevance_role=decision.relevance_role or None,
                labels=labels,
            )
        except ValueError:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "invalid action page request")
        return None
    page = session.current_action_page
    if page is None or decision.action_id not in page.visible_action_ids:
        return build_result(
            AgentLoopStatus.BLOCKED,
            task,
            state,
            0,
            0,
            "policy selected outside the current action page",
        )
    return await execute_selection(session, action_space, decision)


def ensure_current_action_page(
    session: AgentRunSession,
    action_space: ActionSpace,
    pager: ActionPager,
) -> None:
    if session.current_action_space is not None and session.current_action_space.action_space_id == action_space.action_space_id:
        return
    labels = {item.target_id: item.label for item in session.state.current_observation.targets}
    session.current_action_space = action_space
    session.current_action_page = pager.page(action_space, session.state.active_objective, labels=labels)


async def _fresh_observation(session: AgentRunSession, decision: AgentDecision, reason: str) -> None | object:
    state = session.state
    if not _can_observe(session):
        return observation_budget_result(session.task, state, 0, 0)
    state.append_turn(Turn(state.current_observation.observation_id, decision))
    previous_id = state.current_observation.observation_id
    try:
        state.current_observation = await observe_fresh(session.environment, previous_id, reason)
    except FreshObservationUnavailable as exc:
        session.observation_count += 1
        return build_result(AgentLoopStatus.FAILED, session.task, state, 0, 0, str(exc))
    session.observation_count += 1
    return None


async def _propose_done(
    session: AgentRunSession,
    decision: ProposeDone,
    task_evaluator: TaskEvaluator,
) -> None | object:
    task, state = session.task, session.state
    index = WorldEvidenceIndex.from_observation(state.current_observation)
    if any(not index.resolve(item) for item in decision.evidence_refs):
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion evidence is not current")
    evaluation = await validated_task_evaluation(task_evaluator, task, state.current_observation)
    state.append_turn(Turn(state.current_observation.observation_id, decision, task_evaluation=evaluation))
    status = task_evaluation_loop_status(evaluation)
    return None if status is None else build_result(status, task, state, 0, 0, evaluation.reason)


def _can_observe(session: AgentRunSession) -> bool:
    return session.observation_count < session.task.loop_budget.max_observations
