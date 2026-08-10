"""Bind, execute, reobserve, and evaluate one admitted action exactly once."""

from __future__ import annotations

from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import (
    untrusted_evaluation_turn,
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.observation_control import FreshObservationUnavailable, observe_fresh
from affordance_runtime.agent.policy import ActionEvaluator, TaskEvaluator
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.progress_control import record_execution_progress
from affordance_runtime.agent.result import build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus, Turn
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
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
    task, state, environment = session.task, session.state, session.environment
    if session.observation_count >= task.loop_budget.max_observations:
        return observation_budget_result(task, state, 0, 0)
    before = state.current_observation
    try:
        request = binder.bind(selection, before, decision.context_id)
    except BindingError:
        try:
            state.current_observation = await observe_fresh(
                environment, before.observation_id, "binding unavailable; refresh world"
            )
        except FreshObservationUnavailable as exc:
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
            return state, 1, 0, 0, terminal
        return state, 1, 0, 0, None
    current = session.current_context_snapshot
    if current is None or request.context_id != current.context_id or session.consumed_context_id != request.context_id:
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "bound request context is not current")
    result = await environment.execute(request)
    probed = _probe_count(result)
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result))
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action result lineage mismatch")
        return state, 0, int(result.dispatch_status != DispatchStatus.NOT_SENT), probed, terminal
    if result.dispatch_status == DispatchStatus.NOT_SENT:
        return await _not_sent_outcome(session, decision, request, result, probed)
    try:
        after = await observe_fresh(environment, before.observation_id, "fresh post-action observation")
    except FreshObservationUnavailable as exc:
        state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result))
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, 1, 1, probed, terminal
    try:
        action_evaluation = await validated_action_evaluation(
            action_evaluator, task, before, request, result, after
        )
    except ValueError as exc:
        state.append_turn(untrusted_evaluation_turn(before.observation_id, decision, request, result, after.observation_id))
        state.current_observation = after
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, 1, 1, probed, terminal
    try:
        task_evaluation = await validated_task_evaluation(task_evaluator, task, after)
    except ValueError as exc:
        state.append_turn(
            untrusted_evaluation_turn(
                before.observation_id, decision, request, result, after.observation_id, action_evaluation
            )
        )
        state.current_observation = after
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, 1, 1, probed, terminal
    state.append_turn(
        Turn(
            before.observation_id,
            decision,
            request.intent,
            request.request_id,
            result,
            after.observation_id,
            action_evaluation,
            task_evaluation,
        )
    )
    state.current_observation = after
    record_execution_progress(
        session, selection, action_evaluation, after, task_evaluation
    )
    post_terminal = post_action_result(task, state, request, result, action_evaluation, task_evaluation)
    return state, 1, 1, probed, post_terminal


def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    return int(value) if isinstance(value, int | float) else 0


async def _not_sent_outcome(session, decision, request, result, probed):
    task, state = session.task, session.state
    before_id = state.current_observation.observation_id
    state.append_turn(Turn(before_id, decision, request.intent, request.request_id, result))
    if result.error not in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action was not dispatched")
        return state, 0, 0, probed, terminal
    try:
        state.current_observation = await observe_fresh(
            session.environment, before_id, "currentness unavailable; refresh world"
        )
    except FreshObservationUnavailable as exc:
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, 1, 0, probed, terminal
    return state, 1, 0, probed, None
