"""Bind, execute once, consume typed after acquisition, and evaluate."""

from __future__ import annotations

from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import (
    untrusted_evaluation_turn,
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.observation_control import (
    acquisition_attempt_count,
    capture_fresh,
    no_fresh_after_result,
    post_action_observation,
)
from affordance_runtime.agent.policy import ActionEvaluator, TaskEvaluator
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.progress_control import record_execution_progress
from affordance_runtime.agent.result import build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus, Turn
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import AdmittedActionSelection


async def execute_cycle(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
    decision: SelectAction,
    binder: ActionBinder,
    action_evaluator: ActionEvaluator,
    task_evaluator: TaskEvaluator,
):
    task, state = session.task, session.state
    if session.observation_count >= task.loop_budget.max_observations:
        return observation_budget_result(task, state, 0, 0)
    before = state.current_observation
    try:
        request = binder.bind(selection, before, decision.context_id)
    except BindingError:
        return await _binding_refresh(session, before.observation_id)
    current = session.current_context_snapshot
    if (
        current is None
        or request.context_id != current.context_id
        or session.consumed_context_id != request.context_id
    ):
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0,
            "bound request context is not current",
        )
    outcome = await session.environment.execute(request)
    result = outcome.result
    probed = _probe_count(result)
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result))
        terminal = build_result(
            AgentLoopStatus.FAILED, task, state, 0, 0, "action result lineage mismatch",
        )
        observed = acquisition_attempt_count(outcome.post_acquisition)
        return state, observed, int(result.dispatch_status is not DispatchStatus.NOT_SENT), probed, terminal
    if result.dispatch_status is DispatchStatus.NOT_SENT:
        return await _not_sent_outcome(session, decision, request, result, probed)
    remaining = task.loop_budget.max_observations - session.observation_count
    acquired = await post_action_observation(
        session.environment, before.observation_id, outcome.post_acquisition, remaining,
    )
    if acquired.observation is None:
        terminal = no_fresh_after_result(session, decision, request, result, acquired)
        return state, acquired.attempts, 1, probed, terminal
    return await _evaluate_after(
        session, selection, decision, request, result, acquired.observation,
        acquired.attempts, probed, action_evaluator, task_evaluator,
    )


async def _evaluate_after(
    session, selection, decision, request, result, after, observed, probed,
    action_evaluator, task_evaluator,
):
    task, state = session.task, session.state
    before = state.current_observation
    try:
        action_evaluation = await validated_action_evaluation(
            action_evaluator, task, before, request, result, after,
        )
    except ValueError as exc:
        state.append_turn(untrusted_evaluation_turn(
            before.observation_id, decision, request, result, after.observation_id,
        ))
        state.current_observation = after
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, observed, 1, probed, terminal
    try:
        task_evaluation = await validated_task_evaluation(task_evaluator, task, after)
    except ValueError as exc:
        state.append_turn(untrusted_evaluation_turn(
            before.observation_id, decision, request, result, after.observation_id,
            action_evaluation,
        ))
        state.current_observation = after
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, observed, 1, probed, terminal
    state.append_turn(Turn(
        before.observation_id, decision, request.intent, request.request_id,
        result, after.observation_id, action_evaluation, task_evaluation,
    ))
    state.current_observation = after
    record_execution_progress(session, selection, action_evaluation, after, task_evaluation)
    terminal = post_action_result(
        task, state, request, result, action_evaluation, task_evaluation,
    )
    return state, observed, 1, probed, terminal


async def _binding_refresh(session: AgentRunSession, previous_id: str):
    acquired = await capture_fresh(
        session.environment,
        previous_id,
        WorldObservationRequest(
            ObservationRequestKind.BINDING_REFRESH,
            "binding unavailable refresh",
        ),
    )
    if acquired.observation is not None:
        session.state.current_observation = acquired.observation
        return session.state, acquired.attempts, 0, 0, None
    terminal = build_result(
        AgentLoopStatus.FAILED,
        session.task,
        session.state,
        0,
        0,
        acquired.reason_code,
        failure_code=acquired.failure_code,
    )
    return session.state, acquired.attempts, 0, 0, terminal


async def _not_sent_outcome(session, decision, request, result: ActionResult, probed):
    task, state = session.task, session.state
    before_id = state.current_observation.observation_id
    state.append_turn(Turn(before_id, decision, request.intent, request.request_id, result))
    if result.error not in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
        terminal = build_result(
            AgentLoopStatus.FAILED, task, state, 0, 0, "action was not dispatched",
        )
        return state, 0, 0, probed, terminal
    acquired = await capture_fresh(
        session.environment,
        before_id,
        WorldObservationRequest(
            ObservationRequestKind.CURRENTNESS_REFRESH,
            "currentness unavailable refresh",
        ),
    )
    if acquired.observation is not None:
        state.current_observation = acquired.observation
        return state, acquired.attempts, 0, probed, None
    terminal = build_result(
        AgentLoopStatus.FAILED, task, state, 0, 0, acquired.reason_code,
        failure_code=acquired.failure_code,
    )
    return state, acquired.attempts, 0, probed, terminal


def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    return int(value) if isinstance(value, int | float) else 0
