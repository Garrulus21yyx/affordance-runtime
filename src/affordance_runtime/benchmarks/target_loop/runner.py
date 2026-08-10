"""Sequential isolated benchmark execution through AgentEpisodeRunner only."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable

from affordance_runtime.agent import (
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    AgentRunSession,
    AgentSessionStartError,
)
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, accept_suite, safe_rate
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    BenchmarkManifest,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    CaseFailureOrigin,
    MetricMeasurement,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingActionEvaluator,
    CountingEnvironment,
    instrument_policy,
    instrument_task_evaluator,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest
from affordance_runtime.benchmarks.target_loop.terminal_reasons import project_terminal_reason_code
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.execution import DispatchStatus


async def run_suite(
    manifest: BenchmarkManifest,
    case_completed: Callable[[int, BenchmarkCaseResult], None] | None = None,
) -> BenchmarkSuiteResult:
    digest = manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create(
        manifest.suite_id, digest, manifest.profile_id, manifest.seed,
    )
    completed = []
    for index, case in enumerate(manifest.cases, 1):
        result = await _run_case(case)
        completed.append(result)
        if case_completed is not None:
            case_completed(index, result)
    results = tuple(completed)
    decisions = tuple(
        accept_case(
            result, case.expected_terminal_statuses, case.required_measurements,
            case.metric_expectations,
        )
        for case, result in zip(manifest.cases, results, strict=True)
    )
    accepted = accept_suite(results, decisions)
    sent_unknown = sum(_measured_int(item, "sent_unknown_count") for item in results)
    stale = sum(_measured_int(item, "stale_opportunities") for item in results)
    rates = {
        "unknown_duplicate_rate": safe_rate(MetricMeasurement(
            sum(_measured_int(item, "duplicate_unknown_attempts") for item in results), True, sent_unknown,
        )),
        "stale_zero_call_rate": safe_rate(MetricMeasurement(
            stale - sum(_measured_int(item, "stale_zero_call_violations") for item in results), True, stale,
        )),
    }
    return BenchmarkSuiteResult(identity, results, accepted, rates)


async def _run_case(case) -> BenchmarkCaseResult:
    instrumentation = BenchmarkInstrumentation()
    environment = None
    result = None
    partial = None
    snapshot = None
    session_holder: dict[str, AgentRunSession] = {}
    failure = ""
    started = time.perf_counter()
    try:
        try:
            environment = case.environment_factory(instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.ENVIRONMENT_FACTORY, "environment_factory_exception", exc,
            )
            raise _CaseStageError("environment factory", exc) from exc
        try:
            task = case.task_factory()
        except Exception as exc:
            instrumentation.record_failure(CaseFailureOrigin.TASK_FACTORY, "task_factory_exception", exc)
            raise _CaseStageError("task factory", exc) from exc
        try:
            composition = case.composition_factory(instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.COMPOSITION_FACTORY, "composition_factory_exception", exc,
            )
            raise _CaseStageError("composition factory", exc) from exc
        counted_environment = CountingEnvironment(
            environment, instrumentation, frozenset(task.forbidden_effects),
        )
        try:
            loop = _build_loop(composition, instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.LOOP_CONSTRUCTION, "loop_construction_exception", exc,
            )
            raise _CaseStageError("AgentLoop construction", exc) from exc
        result = await asyncio.wait_for(
            _run_episode(case, loop, counted_environment, task, instrumentation, session_holder),
            timeout=case.timeout_s,
        )
    except TimeoutError as exc:
        failure = "case timeout"
        instrumentation.record_failure(CaseFailureOrigin.HARNESS_WATCHDOG, "case_timeout", exc)
        session = session_holder.get("session")
        if session is not None:
            partial = session.snapshot_partial_episode()
    except _CaseStageError as exc:
        failure = f"{exc.stage} failed: {type(exc.cause).__name__}"
    except Exception as exc:
        failure = f"case exception: {type(exc).__name__}"
    finally:
        if environment is not None:
            try:
                await _close(environment)
            except Exception as exc:
                instrumentation.record_failure(CaseFailureOrigin.CLEANUP, "cleanup_exception", exc)
                failure = _append_failure(failure, "cleanup failed")
    session = session_holder.get("session")
    if session is not None:
        snapshot = session.snapshot_partial_episode()
    elapsed = (time.perf_counter() - started) * 1000
    return _case_result(case.case_id, result, instrumentation, elapsed, failure, partial, snapshot)


def _build_loop(composition, instrumentation):
    loop = AgentLoop(
        instrument_policy(composition.policy, instrumentation),
        CountingActionEvaluator(composition.action_evaluator, instrumentation),
        instrument_task_evaluator(composition.task_evaluator, instrumentation),
    )
    if composition.risk_policy is not None:
        loop.risk_policy = composition.risk_policy
    return loop


async def _run_episode(case, loop, environment, task, instrumentation, session_holder):
    try:
        session = await AgentEpisodeRunner(loop).start(environment, task)
    except AgentSessionStartError as exc:
        instrumentation.record_failure(CaseFailureOrigin.SESSION_START, exc.reason_code, exc)
        raise
    except Exception as exc:
        instrumentation.record_failure(CaseFailureOrigin.SESSION_START, "session_start_exception", exc)
        raise
    session_holder["session"] = session
    result = await session.run_until_pause()
    if case.auto_confirm and result.status == AgentLoopStatus.WAITING_CONFIRMATION:
        request = result.confirmation_request
        if request is None:
            raise RuntimeError("confirmation status omitted its typed request")
        decision = ConfirmationDecision(
            request.confirmation_id, request.subject_id, ConfirmationDecisionKind.CONFIRM,
        )
        instrumentation.confirmations_submitted += 1
        result = await session.resolve_confirmation(decision)
    return result


async def _close(environment) -> None:
    for name in ("close", "shutdown"):
        method = getattr(environment, name, None)
        if method is None:
            continue
        outcome = method()
        if inspect.isawaitable(outcome):
            await outcome
        return


def _case_result(
    case_id, result, instrumentation, latency_ms, failure, partial=None, snapshot=None,
) -> BenchmarkCaseResult:
    turns = result.turns if result is not None else ()
    sent_unknown = partial.sent_unknown_count if partial is not None else sum(
        item.result is not None and item.result.dispatch_status == DispatchStatus.SENT_UNKNOWN
        for item in turns
    )
    values = _metric_values(result, turns, instrumentation, sent_unknown, partial)
    measurements = {
        name: MetricMeasurement(value, True) for name, value in values.items()
    }
    measurements["duplicate_unknown_attempts"] = MetricMeasurement(
        values["duplicate_unknown_attempts"], True, sent_unknown,
    )
    measurements["stale_zero_call_violations"] = MetricMeasurement(
        values["stale_zero_call_violations"], True, values["stale_opportunities"],
    )
    failure_code = "case_timeout" if failure == "case timeout" else ""
    if result is not None and result.message == "agent loop turn budget exhausted":
        failure_code = "turn_budget_exhausted"
    if result is not None and result.policy_failure is not None:
        failure_code = f"policy_{result.policy_failure.kind}"
    metadata = snapshot or partial
    return BenchmarkCaseResult(
        case_id=case_id,
        status=str(result.status) if result else str(AgentLoopStatus.FAILED),
        execution_completed=result is not None and not failure,
        failure_reason=failure,
        latency_ms=latency_ms,
        measurements=measurements,
        terminal_reason_code=(
            project_terminal_reason_code(result.status, result.message, result.failure_code)
            if result is not None else None
        ),
        termination_origin=(
            "harness_watchdog"
            if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG
            else "cleanup"
            if instrumentation.failure_origin is CaseFailureOrigin.CLEANUP
            else "component"
            if instrumentation.failure_origin is not CaseFailureOrigin.NONE
            else "runtime"
            if result is not None
            else ""
        ),
        case_failure_code=failure_code,
        partial_episode_available=partial is not None,
        latest_semantic_attempt_key_digest=(
            metadata.latest_semantic_attempt_key_digest if metadata is not None else ""
        ),
        same_attempt_streak=metadata.same_attempt_streak if metadata is not None else 0,
        no_progress_count=metadata.no_progress_count if metadata is not None else 0,
        last_progress_event_type=metadata.last_progress_event_type if metadata is not None else "",
        failure_origin=instrumentation.failure_origin,
        failure_code=instrumentation.failure_code,
        exception_class=instrumentation.exception_class,
        last_decision_type=metadata.last_decision_type if metadata is not None else "",
        last_policy_failure_code=(
            str(result.policy_failure.kind) if result is not None and result.policy_failure is not None else ""
        ),
        last_action_space_option_count=(
            metadata.last_action_space_option_count if metadata is not None else 0
        ),
        last_world_target_count=metadata.last_world_target_count if metadata is not None else 0,
        last_world_coverage=metadata.last_world_coverage if metadata is not None else "",
        pending_kind=metadata.pending_kind if metadata is not None else "",
        latest_task_status=metadata.latest_task_status if metadata is not None else "",
        latest_action_evaluation_status=(
            metadata.latest_action_evaluation_status if metadata is not None else ""
        ),
    )


def _metric_values(result, turns, state, sent_unknown, partial=None) -> dict[str, int]:
    metadata = state.model_metadata
    observations = result.observation_count if result else partial.observation_count if partial else 0
    executions = result.execution_count if result else partial.execution_count if partial else 0
    probes = result.currentness_probe_count if result else partial.currentness_probe_count if partial else 0
    completed_turns = len(turns) if result else partial.completed_turn_count if partial else 0
    values = {
        "observations": observations,
        "executions": executions,
        "currentness_probes": probes,
        "turns": completed_turns,
        "policy_calls": state.policy_calls,
        "semantic_judge_calls": state.semantic_judge_calls,
        "provider_attempts": state.provider_attempts,
        "confirmations": state.confirmations_submitted,
        "ask_user_count": sum(item.decision.__class__.__name__ == "AskUser" for item in turns),
        "wait_count": sum(item.decision.__class__.__name__ == "Wait" for item in turns),
        "page_request_count": sum(item.decision.__class__.__name__ == "RequestActionPage" for item in turns),
        "sent_unknown_count": sent_unknown,
        "duplicate_unknown_attempts": state.duplicate_unknown_attempts,
        "forbidden_effect_attempts": state.forbidden_effect_attempts,
        "stale_opportunities": state.stale_opportunities,
        "stale_zero_call_violations": state.stale_zero_call_violations,
        "effectful_dispatches": state.effectful_dispatches,
        "reset_acquisitions": state.environment_reset_acquisitions,
        "independent_capture_calls": state.environment_capture_calls,
        "post_action_acquisitions": state.environment_post_acquisitions,
        "provider_retry_count": (
            metadata.rate_limit_retry_count + metadata.transient_retry_count
            if metadata is not None else -1
        ),
        "prompt_tokens": state.prompt_tokens,
        "completion_tokens": state.completion_tokens,
        "total_tokens": state.total_tokens,
        "model_latency_ms": state.model_latency_ms,
    }
    values.update(state.custom_metrics)
    return values


class _CaseStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause = cause
        super().__init__(stage)


def _append_failure(current: str, addition: str) -> str:
    return f"{current}; {addition}" if current else addition


def _measured_int(result: BenchmarkCaseResult, name: str) -> int:
    measurement = result.measurements[name]
    if not measurement.measured or not isinstance(measurement.value, int):
        raise ValueError(f"benchmark metric {name} is not a measured integer")
    return measurement.value
