import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_internal_safety_sent_unknown_and_provider_failure_are_zero_replay() -> None:
    cases = get_manifest("internal-safety", "scripted-model", 7)
    result = asyncio.run(run_suite("internal-safety", "scripted-model", cases, 7))
    assert result.acceptance.accepted
    sent, confirmation, stale, failure, forbidden = result.cases
    assert sent.sent_unknown_count == 1 and sent.duplicate_unknown_attempts == 0
    assert stale.stale_opportunities == 1 and stale.stale_zero_call_violations == 0
    assert failure.executions == 0
    assert confirmation.confirmations == 1 and confirmation.executions == 1
    assert forbidden.forbidden_effect_attempts == 0
