"""Sequential isolated benchmark execution through the production TargetRuntime."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from affordance_runtime.agent.core_loop import CoreLoopStartError
from affordance_runtime.agent.episode_snapshot import snapshot_episode
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.app.composition import compose_target_runtime
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
    instrument_policy,
    instrument_task_evaluator,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest


async def run_suite(
    manifest: BenchmarkManifest,
    case_completed: Callable[[int, BenchmarkCaseResult], None] | None = None,
    trace_dir: Path | None = None,
) -> BenchmarkSuiteResult:
    digest = manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create(
        manifest.suite_id,
        digest,
        manifest.profile_id,
        manifest.seed,
    )
    completed = []
    for index, case in enumerate(manifest.cases, 1):
        result = replace(
            await _run_case(case, trace_dir=trace_dir),
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
            result,
            case.expected_terminal_statuses,
            case.required_measurements,
            case.metric_expectations,
        )
        for case, result in zip(manifest.cases, results, strict=True)
    )
    accepted = accept_suite(results, decisions)
    sent_unknown = sum(_measured_int(item, "sent_unknown_count") for item in results)
    stale = sum(_measured_int(item, "stale_opportunities") for item in results)
    rates = {
        "unknown_duplicate_rate": safe_rate(
            MetricMeasurement(
                sum(_measured_int(item, "duplicate_unknown_attempts") for item in results),
                True,
                sent_unknown,
            )
        ),
        "stale_zero_call_rate": safe_rate(
            MetricMeasurement(
                stale - sum(_measured_int(item, "stale_zero_call_violations") for item in results),
                True,
                stale,
            )
        ),
    }
    return BenchmarkSuiteResult(identity, results, accepted, rates)


async def _run_case(case, *, trace_dir: Path | None = None) -> BenchmarkCaseResult:
    instrumentation = BenchmarkInstrumentation(
        trace_recorder=RunTraceRecorder(
            trace_dir / "traces" / case.case_id if trace_dir is not None else None
        )
    )
    environment = None
    result = None
    partial = None
    snapshot = None
    state_holder: dict[str, RunState] = {}
    failure = ""
    started = time.perf_counter()
    try:
        try:
            environment = case.environment_factory(instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.ENVIRONMENT_FACTORY,
                "environment_factory_exception",
                exc,
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
                CaseFailureOrigin.COMPOSITION_FACTORY,
                "composition_factory_exception",
                exc,
            )
            raise _CaseStageError("composition factory", exc) from exc
        counted_environment = CountingEnvironment(
            environment,
            instrumentation,
            frozenset(task.forbidden_effects),
        )
        try:
            runtime = _build_runtime(composition, instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.LOOP_CONSTRUCTION,
                "loop_construction_exception",
                exc,
            )
            raise _CaseStageError("CoreAgentLoop construction", exc) from exc
        result = await _run_with_watchdog(
            _run_episode(case, runtime, counted_environment, task, instrumentation, state_holder),
            case.timeout_s,
        )
    except _HarnessWatchdogTimeout as exc:
        failure = "case timeout"
        instrumentation.record_watchdog("case_timeout", exc)
        state = state_holder.get("state")
        if state is not None:
            partial = snapshot_episode(state)
    except _CaseStageError as exc:
        failure = f"{exc.stage} failed: {type(exc.cause).__name__}"
    except Exception as exc:
        failure = f"case exception: {type(exc).__name__}"
        instrumentation.record_failure(
            CaseFailureOrigin.UNKNOWN,
            "runtime_exception",
            exc,
        )
        result = state_holder.get("state")
    finally:
        if environment is not None:
            try:
                await _close(environment)
            except Exception as exc:
                instrumentation.record_cleanup_failure("cleanup_exception", exc)
                failure = _append_failure(failure, "cleanup failed")
    state = state_holder.get("state")
    if state is not None:
        snapshot = snapshot_episode(state)
    instrumentation.set_custom_metric(
        "trace_recording_failures", len(instrumentation.trace_recorder.errors)
    )
    if instrumentation.trace_recorder.errors:
        failure = _append_failure(failure, "trace recording failed")
    elapsed = (time.perf_counter() - started) * 1000
    return project_case_result(
        case.case_id,
        result,
        instrumentation,
        elapsed,
        failure,
        timeout_snapshot=partial,
        final_snapshot=snapshot,
    )


def _build_runtime(composition, instrumentation):
    return compose_target_runtime(
        instrument_policy(composition.policy, instrumentation),
        CountingActionEvaluator(composition.action_evaluator, instrumentation),
        instrument_task_evaluator(composition.task_evaluator, instrumentation),
        risk_policy=composition.risk_policy,
        required_decisions=composition.required_decisions,
        trace_sink=instrumentation,
    )


async def _run_episode(case, runtime, environment, task, instrumentation, state_holder):
    try:
        state = await runtime.initialize_task(environment, task)
    except CoreLoopStartError as exc:
        instrumentation.record_failure(CaseFailureOrigin.ENVIRONMENT_RESET, exc.reason_code, exc)
        raise
    except Exception as exc:
        instrumentation.record_failure(CaseFailureOrigin.SESSION_START, "session_start_exception", exc)
        raise
    state_holder["state"] = state
    result = await runtime.continue_task(environment, task, state)
    if case.auto_confirm and result.status is RunStatus.WAITING_CONFIRMATION:
        instrumentation.confirmations_submitted += 1
        result = await runtime.resume_confirmation(
            environment,
            task,
            result,
            approved=True,
        )
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
