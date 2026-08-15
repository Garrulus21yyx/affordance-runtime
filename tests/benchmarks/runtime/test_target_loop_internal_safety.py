import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_internal_safety_sent_unknown_and_provider_failure_are_zero_replay() -> None:
    manifest = get_manifest("internal-safety", "scripted-model", 7)
    result = asyncio.run(run_suite(manifest))
    assert result.acceptance.accepted
    sent, confirmation, stale, failure, forbidden = result.cases
    assert sent.measurements["sent_unknown_count"].value == 1
    assert sent.measurements["duplicate_unknown_attempts"].value == 0
    assert stale.measurements["stale_opportunities"].value == 1
    assert stale.measurements["stale_zero_call_violations"].value == 0
    assert failure.measurements["executions"].value == 0
    assert confirmation.measurements["confirmations"].value == 1
    assert confirmation.measurements["executions"].value == 1
    assert forbidden.measurements["forbidden_effect_attempts"].value == 0
