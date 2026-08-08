"""Sequential isolated benchmark execution through AgentEpisodeRunner only."""

from __future__ import annotations

import asyncio
import inspect
import time

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
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
    sent_unknown = sum(item.sent_unknown_count for item in results)
    stale = sum(item.stale_opportunities for item in results)
    rates = {
        "unknown_duplicate_rate": safe_rate(MetricMeasurement(
            sum(item.duplicate_unknown_attempts for item in results), True, sent_unknown,
        )),
        "stale_zero_call_rate": safe_rate(MetricMeasurement(
            stale - sum(item.stale_zero_call_violations for item in results), True, stale,
        )),
    }
    return BenchmarkSuiteResult(identity, results, accepted, rates)


async def _run_case(case) -> BenchmarkCaseResult:
    instrumentation = BenchmarkInstrumentation()
    environment = None
    result = None
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
            _run_episode(case, loop, counted_environment, task, instrumentation),
            timeout=case.timeout_s,
        )
    except TimeoutError:
        failure = "case timeout"
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
    return _case_result(case.case_id, result, instrumentation, elapsed, failure)


def _build_loop(composition, instrumentation):
    loop = AgentLoop(
        instrument_policy(composition.policy, instrumentation),
        CountingActionEvaluator(composition.action_evaluator, instrumentation),
        instrument_task_evaluator(composition.task_evaluator, instrumentation),
    )
    if composition.risk_policy is not None:
        loop.risk_policy = composition.risk_policy
    return loop


async def _run_episode(case, loop, environment, task, instrumentation):
    session = await AgentEpisodeRunner(loop).start(environment, task)
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


def _case_result(case_id, result, instrumentation, latency_ms, failure) -> BenchmarkCaseResult:
    turns = result.turns if result is not None else ()
    sent_unknown = sum(
        item.result is not None and item.result.dispatch_status == DispatchStatus.SENT_UNKNOWN
        for item in turns
    )
    values = _metric_values(result, turns, instrumentation, sent_unknown)
    measurements = {
        name: MetricMeasurement(value, True) for name, value in values.items()
    }
    measurements["duplicate_unknown_attempts"] = MetricMeasurement(
        values["duplicate_unknown_attempts"], True, sent_unknown,
    )
    measurements["stale_zero_call_violations"] = MetricMeasurement(
        values["stale_zero_call_violations"], True, values["stale_opportunities"],
    )
    contract_values = {
        name: values[name] for name in (
            "observations", "executions", "currentness_probes", "turns", "policy_calls",
            "semantic_judge_calls", "provider_attempts", "confirmations", "ask_user_count",
            "wait_count", "page_request_count", "sent_unknown_count", "duplicate_unknown_attempts",
            "forbidden_effect_attempts", "stale_opportunities", "stale_zero_call_violations",
            "effectful_dispatches",
        )
    }
    return BenchmarkCaseResult(
        case_id=case_id,
        status=str(result.status) if result else str(AgentLoopStatus.FAILED),
        execution_completed=result is not None and not failure,
        failure_reason=failure,
        latency_ms=latency_ms,
        measurements=measurements,
        **contract_values,
    )


def _metric_values(result, turns, state, sent_unknown) -> dict[str, int]:
    values = {
        "observations": result.observation_count if result else 0,
        "executions": result.execution_count if result else 0,
        "currentness_probes": result.currentness_probe_count if result else 0,
        "turns": len(turns),
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
