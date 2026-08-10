"""Sequential isolated benchmark execution through AgentEpisodeRunner only."""

from __future__ import annotations

import asyncio
import inspect
import time

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, AgentRunSession
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, accept_suite, safe_rate
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    BenchmarkManifest,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
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


async def run_suite(manifest: BenchmarkManifest) -> BenchmarkSuiteResult:
    digest = manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create(
        manifest.suite_id, digest, manifest.profile_id, manifest.seed,
    )
    results = tuple([await _run_case(case) for case in manifest.cases])
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
    session_holder: dict[str, AgentRunSession] = {}
    failure = ""
    started = time.perf_counter()
    try:
        try:
            environment = case.environment_factory(instrumentation)
        except Exception as exc:
            raise _CaseStageError("environment factory", exc) from exc
        try:
            task = case.task_factory()
            composition = case.composition_factory(instrumentation)
        except Exception as exc:
            raise _CaseStageError("composition factory", exc) from exc
        counted_environment = CountingEnvironment(
            environment, instrumentation, frozenset(task.forbidden_effects),
        )
        try:
            loop = _build_loop(composition, instrumentation)
        except Exception as exc:
            raise _CaseStageError("AgentLoop construction", exc) from exc
        result = await asyncio.wait_for(
            _run_episode(case, loop, counted_environment, task, instrumentation, session_holder),
            timeout=case.timeout_s,
        )
    except TimeoutError:
        failure = "case timeout"
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
            except Exception:
                failure = _append_failure(failure, "cleanup failed")
    elapsed = (time.perf_counter() - started) * 1000
    return _case_result(case.case_id, result, instrumentation, elapsed, failure, partial)


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
    session = await AgentEpisodeRunner(loop).start(environment, task)
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


def _case_result(case_id, result, instrumentation, latency_ms, failure, partial=None) -> BenchmarkCaseResult:
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
        termination_origin="harness_watchdog" if failure == "case timeout" else "",
        case_failure_code="case_timeout" if failure == "case timeout" else "",
        partial_episode_available=partial is not None,
        latest_task_status=partial.latest_task_status if partial is not None else "",
        latest_action_evaluation_status=(
            partial.latest_action_evaluation_status if partial is not None else ""
        ),
        latest_semantic_attempt_key_digest=(
            partial.latest_semantic_attempt_key_digest if partial is not None else ""
        ),
        same_attempt_streak=partial.same_attempt_streak if partial is not None else 0,
        no_progress_count=partial.no_progress_count if partial is not None else 0,
        last_progress_event_type=partial.last_progress_event_type if partial is not None else "",
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
