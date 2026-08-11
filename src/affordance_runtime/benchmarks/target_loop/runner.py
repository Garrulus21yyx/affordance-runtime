"""Sequential isolated benchmark execution through AgentEpisodeRunner only."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import replace

from affordance_runtime.agent import (
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    AgentRunSession,
    AgentSessionStartError,
)
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, accept_suite, safe_rate
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
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
    finalize_policy_trace,
    instrument_policy,
    instrument_task_evaluator,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind


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
        result = replace(
            await _run_case(case),
            suite_id=identity.suite_id,
            profile_id=identity.profile_id,
            seed=identity.seed,
            manifest_digest=identity.manifest_digest,
            harness_schema_version=identity.harness_schema_version,
        )
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
        result = await _run_with_watchdog(
            _run_episode(case, loop, counted_environment, task, instrumentation, session_holder),
            case.timeout_s,
        )
    except _HarnessWatchdogTimeout as exc:
        failure = "case timeout"
        instrumentation.record_watchdog("case_timeout", exc)
        session = session_holder.get("session")
        if session is not None:
            partial = session.snapshot_partial_episode()
    except _CaseStageError as exc:
        failure = f"{exc.stage} failed: {type(exc.cause).__name__}"
    except Exception as exc:
        failure = f"case exception: {type(exc).__name__}"
        instrumentation.record_failure(
            CaseFailureOrigin.UNKNOWN, "runtime_exception", exc,
        )
        session = session_holder.get("session")
        if session is not None and session.last_result is not None:
            # The session latches canonical typed failure truth before preserving
            # the component exception behavior. Keep that authority for v7 facts.
            result = session.last_result
    finally:
        if environment is not None:
            try:
                await _close(environment)
            except Exception as exc:
                instrumentation.record_cleanup_failure("cleanup_exception", exc)
                failure = _append_failure(failure, "cleanup failed")
    session = session_holder.get("session")
    if session is not None:
        snapshot = session.snapshot_partial_episode()
    elapsed = (time.perf_counter() - started) * 1000
    finalize_policy_trace(instrumentation, result)
    return project_case_result(
        case.case_id,
        result,
        instrumentation,
        elapsed,
        failure,
        timeout_snapshot=partial,
        final_snapshot=snapshot,
    )


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
        instrumentation.record_failure(CaseFailureOrigin.ENVIRONMENT_RESET, exc.reason_code, exc)
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


async def _run_with_watchdog(awaitable, timeout_s: float):
    """Own the deadline explicitly so component TimeoutError remains component truth."""
    task = asyncio.create_task(awaitable)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout_s)
        if task in done:
            return task.result()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise _HarnessWatchdogTimeout
    except asyncio.CancelledError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


class _CaseStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause = cause
        super().__init__(stage)


class _HarnessWatchdogTimeout(RuntimeError):
    """Private sentinel raised only by the harness-owned deadline."""


def _append_failure(current: str, addition: str) -> str:
    return f"{current}; {addition}" if current else addition


def _measured_int(result: BenchmarkCaseResult, name: str) -> int:
    measurement = result.measurements[name]
    if not measurement.measured or not isinstance(measurement.value, int):
        raise ValueError(f"benchmark metric {name} is not a measured integer")
    return measurement.value
