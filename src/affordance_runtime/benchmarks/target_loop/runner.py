"""Sequential isolated execution through AgentEpisodeRunner only."""

from __future__ import annotations

import asyncio
import inspect
import time

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, accept_suite, safe_rate
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest
from affordance_runtime.benchmarks.target_loop.metrics import (
    CounterState,
    CountingActionEvaluator,
    CountingPolicy,
    CountingTaskEvaluator,
)
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.execution import ActionError, DispatchStatus


async def run_suite(suite_id: str, profile_id: str, cases, seed: int) -> BenchmarkSuiteResult:
    cases = tuple(cases)
    if not cases:
        raise ValueError("fixed benchmark manifest cannot be empty")
    identity = BenchmarkRunIdentity.create(suite_id, manifest_digest(tuple(item.case_id for item in cases)), profile_id, seed)
    results, decisions = [], []
    for case in cases:
        result = await _run_case(case)
        results.append(result)
        decisions.append(accept_case(result, case.expected_terminal_statuses, case.required_metrics))
    accepted = accept_suite(tuple(results), tuple(decisions))
    sent_unknown = sum(item.sent_unknown_count for item in results)
    stale = sum(item.stale_opportunities for item in results)
    rates = {
        "unknown_duplicate_rate": safe_rate(sum(item.duplicate_unknown_attempts for item in results), sent_unknown),
        "stale_zero_call_rate": safe_rate(stale - sum(item.stale_zero_call_violations for item in results), stale),
    }
    return BenchmarkSuiteResult(identity, tuple(results), accepted, rates)


async def _run_case(case) -> BenchmarkCaseResult:
    environment = case.environment_factory()
    composition = case.composition_factory()
    counters = CounterState()
    loop = AgentLoop(
        CountingPolicy(composition.policy, counters),
        CountingActionEvaluator(composition.action_evaluator, counters),
        CountingTaskEvaluator(composition.task_evaluator, counters),
    )
    if composition.risk_policy is not None:
        loop.risk_policy = composition.risk_policy
    started = time.perf_counter()
    result, failure = None, ""
    try:
        result = await asyncio.wait_for(_run_episode(case, loop, environment), timeout=case.timeout_s)
    except TimeoutError:
        failure = "case timeout"
    except Exception as exc:
        failure = f"case exception: {type(exc).__name__}"
    try:
        await _close(environment)
    except Exception:
        failure = f"{failure}; cleanup failed" if failure else "cleanup failed"
    elapsed = (time.perf_counter() - started) * 1000
    return _case_result(case.case_id, result, counters, elapsed, failure, environment)


async def _run_episode(case, loop, environment):
    session = await AgentEpisodeRunner(loop).start(environment, case.task_factory())
    result = await session.run_until_pause()
    if case.auto_confirm and result.status == AgentLoopStatus.WAITING_CONFIRMATION:
        request = result.confirmation_request
        assert request is not None
        decision = ConfirmationDecision(
            request.confirmation_id, request.subject_id, ConfirmationDecisionKind.CONFIRM
        )
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


def _case_result(case_id, result, counters, latency_ms, failure, environment) -> BenchmarkCaseResult:
    turns = result.turns if result is not None else ()
    sent_unknown = sum(
        item.result is not None and item.result.dispatch_status == DispatchStatus.SENT_UNKNOWN for item in turns
    )
    stale = sum(
        item.result is not None and item.result.dispatch_status == DispatchStatus.NOT_SENT
        and item.result.error in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}
        for item in turns
    )
    return BenchmarkCaseResult(
        case_id, str(result.status) if result else str(AgentLoopStatus.FAILED), not failure, failure,
        result.observation_count if result else 0, result.execution_count if result else 0,
        result.currentness_probe_count if result else 0, len(turns), counters.policy_calls,
        counters.semantic_judge_calls, counters.provider_attempts,
        int(case_id == "confirmation-fresh-rebind" and result is not None and result.execution_count == 1),
        sum(item.decision.__class__.__name__ == "AskUser" for item in turns),
        sum(item.decision.__class__.__name__ == "Wait" for item in turns),
        sum(item.decision.__class__.__name__ == "RequestActionPage" for item in turns),
        sent_unknown, _duplicate_unknown(turns),
        int(getattr(environment, "benchmark_forbidden_effect_attempts", 0)),
        stale, 0, latency_ms,
    )


def _duplicate_unknown(turns) -> int:
    unknown_intents = {
        _intent_key(item.intent) for item in turns
        if item.result is not None and item.result.dispatch_status == DispatchStatus.SENT_UNKNOWN
    }
    return sum(
        _intent_key(item.intent) in unknown_intents and item.result is not None
        and item.result.dispatch_status != DispatchStatus.SENT_UNKNOWN for item in turns
    )


def _intent_key(intent) -> tuple[str, str, str]:
    if intent is None:
        return ("", "", "")
    return (intent.semantic_action, intent.target_id, intent.destination_id)
