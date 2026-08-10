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
from affordance_runtime.agent.observation_control import (
    capture_admission_failure,
    capture_fresh,
)
from affordance_runtime.agent.policy import AgentPolicy, PolicyFailure, TaskEvaluator
from affordance_runtime.agent.result import build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus, Turn
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.agent.waiting import MAX_TOTAL_WAIT_MS, WaitController
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest
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
        waited_ms=session.waited_ms,
        context_generation=session.next_context_generation(),
        observation_capabilities=session.environment.observation_capabilities,
    )
    session.current_context_snapshot = context
    outcome = await policy.decide(context)
    state.remaining_turns -= 1
    if isinstance(outcome, PolicyFailure):
        return build_result(
            AgentLoopStatus.FAILED,
            task,
            state,
            0,
            0,
            outcome.reason,
            policy_failure=outcome,
        )
    decision = outcome
    if not accept_current_decision(session, decision):
        return None
    if isinstance(decision, AskUser):
        state.append_turn(Turn(state.current_observation.observation_id, decision))
        state.set_pending_question(decision.question)
        return build_result(AgentLoopStatus.WAITING_USER, task, state, 0, 0, decision.question)
    if isinstance(decision, Abort):
        state.append_turn(Turn(state.current_observation.observation_id, decision))
        return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, decision.reason)
    if isinstance(decision, ProposeDone):
        return await _propose_done(session, decision, task_evaluator)
    if isinstance(decision, RequestObservation):
        return await _policy_observation(session, decision)
    if isinstance(decision, Wait):
        return await _wait_refresh(session, decision, waiter)
    if isinstance(decision, RequestActionPage):
        return _request_action_page(session, action_space, context_builder, decision)
    rejection = _current_page_selection_rejection(session, decision)
    if rejection:
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, rejection)
    return await execute_selection(session, action_space, decision)


async def _policy_observation(session: AgentRunSession, decision: RequestObservation):
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        decision.reason,
        decision.subject_id,
        decision.modality,
        decision.required_assurance,
    )
    return await _fresh_observation(session, decision, request)


async def _wait_refresh(session: AgentRunSession, decision: Wait, waiter: WaitController):
    task, state = session.task, session.state
    if not _can_observe(session):
        return observation_budget_result(task, state, 0, 0)
    request = WorldObservationRequest(
        ObservationRequestKind.WAIT_REFRESH, "fresh observation after wait",
    )
    unavailable = capture_admission_failure(session.environment, request)
    if unavailable is not None:
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0, unavailable.reason_code,
            failure_code=unavailable.failure_code,
        )
    if session.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
        state.append_turn(Turn(
            state.current_observation.observation_id,
            decision,
            decision_result="wait_budget_exceeded",
        ))
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0, "total wait budget exhausted",
        )
    await waiter.wait(decision.max_wait_ms)
    session.waited_ms += decision.max_wait_ms
    return await _fresh_observation(session, decision, request)


def ensure_current_action_page(
    session: AgentRunSession,
    action_space: ActionSpace,
    context_builder: ContextBuilder,
) -> None:
    candidate = context_builder.page(action_space, session.state)
    if (
        session.current_action_space is not None
        and session.current_action_space.action_space_id == action_space.action_space_id
        and session.current_action_page is not None
        and session.current_action_page.objective_digest == candidate.objective_digest
    ):
        return
    session.current_action_space = action_space
    session.current_action_page = candidate


async def _fresh_observation(
    session: AgentRunSession,
    decision: AgentDecision,
    request: WorldObservationRequest,
) -> None | object:
    state = session.state
    if not _can_observe(session):
        return observation_budget_result(session.task, state, 0, 0)
    state.append_turn(Turn(state.current_observation.observation_id, decision))
    previous_id = state.current_observation.observation_id
    acquired = await capture_fresh(session.environment, previous_id, request)
    session.observation_count += acquired.attempts
    if acquired.observation is None:
        status = (
            AgentLoopStatus.BLOCKED
            if acquired.attempts == 0 else AgentLoopStatus.FAILED
        )
        return build_result(
            status,
            session.task,
            state,
            0,
            0,
            acquired.reason_code,
            failure_code=acquired.failure_code,
        )
    state.current_observation = acquired.observation
    return None


async def _propose_done(
    session: AgentRunSession,
    decision: ProposeDone,
    task_evaluator: TaskEvaluator,
) -> None | object:
    task, state = session.task, session.state
    index = WorldEvidenceIndex.from_observation(state.current_observation)
    known = {criterion_id(item) for item in task.success_criteria}
    if len(set(decision.claimed_criteria)) != len(decision.claimed_criteria) or not set(decision.claimed_criteria).issubset(known):
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion claim contains an unknown or duplicate criterion")
    if decision.unresolved_items:
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion claim retains unresolved items")
    if any(not index.resolve(item) for item in decision.evidence_refs):
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion evidence is not current")
    evaluation = await validated_task_evaluation(task_evaluator, task, state.current_observation)
    state.append_turn(Turn(state.current_observation.observation_id, decision, task_evaluation=evaluation))
    status = task_evaluation_loop_status(evaluation)
    return None if status is None else build_result(status, task, state, 0, 0, evaluation.reason)


def _can_observe(session: AgentRunSession) -> bool:
    return session.observation_count < session.task.loop_budget.max_observations


def _valid_page_request(session: AgentRunSession, decision: RequestActionPage) -> bool:
    if not decision.cursor:
        return True
    page = session.current_action_page
    if page is None or decision.cursor != page.next_cursor:
        return False
    role = page.relevance_role.value if page.relevance_role else ""
    return (
        decision.query == page.query
        and decision.target_id == page.target_id
        and decision.relevance_role == role
    )


def _request_action_page(
    session: AgentRunSession,
    action_space: ActionSpace,
    context_builder: ContextBuilder,
    decision: RequestActionPage,
) -> object | None:
    if not _valid_page_request(session, decision):
        return build_result(AgentLoopStatus.BLOCKED, session.task, session.state, 0, 0, "invalid action page request")
    previous_page_id = session.current_action_page.page_id if session.current_action_page else ""
    try:
        session.current_action_page = context_builder.page(
            action_space,
            session.state,
            query=decision.query,
            target_id=decision.target_id,
            relevance_role=decision.relevance_role,
            cursor=decision.cursor,
        )
    except ValueError:
        return build_result(AgentLoopStatus.BLOCKED, session.task, session.state, 0, 0, "invalid action page request")
    result = "page_unchanged" if session.current_action_page.page_id == previous_page_id else "page_changed"
    session.state.append_turn(
        Turn(session.state.current_observation.observation_id, decision, decision_result=result)
    )
    return None


def _current_page_selection_rejection(session: AgentRunSession, decision: SelectAction) -> str:
    page = session.current_action_page
    if page is None or decision.action_id not in page.visible_action_ids:
        return "policy selected outside the current action page"
    if decision.destination_id and decision.destination_id not in page.visible_destination_ids(decision.action_id):
        return "policy selected a destination outside the current action page"
    return ""
