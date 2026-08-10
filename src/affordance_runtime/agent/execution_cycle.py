"""Bind, execute once, consume typed after acquisition, and evaluate."""

from __future__ import annotations

from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlContinuationScope,
    ControlTransitionScope,
)
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import (
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.observation_control import (
    acquisition_attempt_count,
    capture_for_session,
    no_fresh_after_result,
    post_action_fallback_result,
    validate_fresh_acquisition,
)
from affordance_runtime.agent.policy import ActionEvaluator, TaskEvaluator
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.progress_control import record_execution_progress
from affordance_runtime.agent.result import build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import AdmittedActionSelection


async def execute_cycle(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
    decision: SelectAction,
    binder: ActionBinder,
    action_evaluator: ActionEvaluator,
    task_evaluator: TaskEvaluator,
    scope: ControlTransitionScope | ControlContinuationScope,
):
    task, state = session.task, session.state
    scope.record_admission(AdmissionStatus.ADMITTED, "action_admitted")
    if session.observation_count >= task.loop_budget.max_observations:
        scope.set_reason("observation_budget_exhausted")
        return observation_budget_result(task, state, 0, 0)
    before = state.current_observation
    try:
        request = binder.bind(selection, before, decision.context_id)
    except BindingError:
        return await _binding_refresh(session, before.observation_id, scope)
    current = session.current_context_snapshot
    if (
        current is None
        or request.context_id != current.context_id
        or session.consumed_context_id != request.context_id
    ):
        scope.set_reason("stale_bound_request")
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0,
            "bound request context is not current",
        )
    outcome = await session.environment.execute(request)
    result = outcome.result
    probe_error = False
    try:
        probed = _probe_count(result)
    except ValueError:
        probed = 0
        probe_error = True
    scope.record_execution(request.request_id, request.intent, result, probed)
    primary = validate_fresh_acquisition(
        outcome.post_acquisition,
        before.observation_id,
        expected_origin=AcquisitionOrigin.POST_ACTION,
        post_action=True,
    )
    if result.dispatch_status is not DispatchStatus.NOT_SENT or primary.attempts:
        scope.record_acquisition(
            primary.status,
            outcome.post_acquisition.origin,
            primary.reason_code,
            primary.attempts,
            expected_origin=AcquisitionOrigin.POST_ACTION,
        )
    primary_attempts = acquisition_attempt_count(outcome.post_acquisition)
    session.observation_count += primary_attempts
    session.execution_count += int(result.dispatch_status is not DispatchStatus.NOT_SENT)
    session.currentness_probe_count += probed
    if probe_error:
        scope.set_reason("invalid_currentness_probe_count")
        terminal = build_result(
            AgentLoopStatus.FAILED, task, state, 0, 0,
            "adapter returned invalid currentness probe metadata",
            reason_code="invalid_currentness_probe_count",
        )
        return state, 0, 0, 0, terminal
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        scope.set_reason("action_result_lineage_mismatch")
        terminal = build_result(
            AgentLoopStatus.FAILED, task, state, 0, 0, "action result lineage mismatch",
        )
        return state, 0, 0, 0, terminal
    if result.dispatch_status is DispatchStatus.NOT_SENT:
        return await _not_sent_outcome(session, decision, request, result, scope)
    remaining = task.loop_budget.max_observations - session.observation_count
    acquired = primary
    if (
        acquired.observation is None
        and session.environment.observation_capabilities.independent_capture
        and primary.attempts < remaining
    ):
        fallback_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action acquisition fallback",
        )
        fallback = await capture_for_session(
            session, before.observation_id, fallback_request, scope,
        )
        acquired = post_action_fallback_result(primary, fallback)
    if acquired.observation is None:
        terminal = no_fresh_after_result(session, decision, request, result, acquired, scope)
        return state, 0, 0, 0, terminal
    state.current_observation = acquired.observation
    state.current_task_evaluation = None
    scope.record_after(acquired.observation.observation_id)
    return await _evaluate_after(
        session, selection, decision, request, result, before, acquired.observation,
        0, 0, action_evaluator, task_evaluator,
        scope,
    )


async def _evaluate_after(
    session, selection, decision, request, result, before, after, observed, probed,
    action_evaluator, task_evaluator,
    scope,
):
    task, state = session.task, session.state
    try:
        action_evaluation = await validated_action_evaluation(
            action_evaluator, task, before, request, result, after,
        )
    except ValueError as exc:
        scope.record_evaluations()
        scope.set_reason("action_evaluation_invalid")
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, observed, 0, probed, terminal
    scope.record_evaluations(action=action_evaluation)
    try:
        task_evaluation = await validated_task_evaluation(task_evaluator, task, after)
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, str(exc))
        return state, observed, 0, probed, terminal
    scope.record_evaluations(task=task_evaluation)
    state.current_task_evaluation = task_evaluation
    record_execution_progress(session, selection, action_evaluation, after, task_evaluation)
    scope.set_reason(f"action_{action_evaluation.status}")
    terminal = post_action_result(
        task, state, request, result, action_evaluation, task_evaluation,
    )
    task_status = task_evaluation_loop_status(task_evaluation)
    if task_status is not None:
        scope.set_reason(f"task_{task_evaluation.status}")
    elif terminal is not None and state.pending_unknown_request is not None:
        scope.set_reason("effect_unknown")
    elif terminal is not None:
        scope.set_reason("action_rejected")
    return state, observed, 0, probed, terminal


async def _binding_refresh(
    session: AgentRunSession,
    previous_id: str,
    scope: ControlTransitionScope | ControlContinuationScope,
):
    acquired = await capture_for_session(
        session,
        previous_id,
        WorldObservationRequest(
            ObservationRequestKind.BINDING_REFRESH,
            "binding unavailable refresh",
        ),
        scope,
    )
    if acquired.observation is not None:
        session.state.current_observation = acquired.observation
        session.state.current_task_evaluation = None
        scope.record_after(acquired.observation.observation_id)
        return session.state, 0, 0, 0, None
    terminal = build_result(
        AgentLoopStatus.FAILED,
        session.task,
        session.state,
        0,
        0,
        acquired.reason_code,
        failure_code=acquired.failure_code,
    )
    return session.state, 0, 0, 0, terminal


async def _not_sent_outcome(
    session,
    decision,
    request,
    result: ActionResult,
    scope: ControlTransitionScope | ControlContinuationScope,
):
    task, state = session.task, session.state
    before_id = state.current_observation.observation_id
    if result.error not in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
        scope.set_reason("action_not_dispatched")
        terminal = build_result(
            AgentLoopStatus.FAILED, task, state, 0, 0, "action was not dispatched",
        )
        return state, 0, 0, 0, terminal
    acquired = await capture_for_session(
        session,
        before_id,
        WorldObservationRequest(
            ObservationRequestKind.CURRENTNESS_REFRESH,
            "currentness unavailable refresh",
        ),
        scope,
    )
    if acquired.observation is not None:
        state.current_observation = acquired.observation
        state.current_task_evaluation = None
        scope.record_after(acquired.observation.observation_id)
        return state, 0, 0, 0, None
    terminal = build_result(
        AgentLoopStatus.FAILED, task, state, 0, 0, acquired.reason_code,
        failure_code=acquired.failure_code,
    )
    return state, 0, 0, 0, terminal


def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    if type(value) is not int or value < 0:
        raise ValueError("currentness probe count must be a non-negative integer")
    return value
