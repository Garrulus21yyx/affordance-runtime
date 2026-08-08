from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, safe_rate
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCaseResult


def _result(**changes):
    values = dict(
        case_id="case", status=str(AgentLoopStatus.DONE), passed=True, failure_reason="",
        observations=2, executions=1, currentness_probes=0, turns=1, policy_calls=1,
        semantic_judge_calls=0, provider_attempts=0, confirmations=0, ask_user_count=0,
        wait_count=0, page_request_count=0, sent_unknown_count=0,
        duplicate_unknown_attempts=0, forbidden_effect_attempts=0,
        stale_opportunities=0, stale_zero_call_violations=0, latency_ms=1.0,
    )
    values.update(changes)
    return BenchmarkCaseResult(**values)


def test_acceptance_fails_closed_for_safety_violation_or_missing_metric() -> None:
    assert accept_case(_result(), (AgentLoopStatus.DONE,), ("executions",)).accepted
    assert not accept_case(_result(forbidden_effect_attempts=1), (AgentLoopStatus.DONE,), ()).accepted
    assert not accept_case(_result(), (AgentLoopStatus.DONE,), ("not_measured",)).accepted
    assert safe_rate(0, 0) is None

