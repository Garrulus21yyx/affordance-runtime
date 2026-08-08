import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_internal_core_deterministic_and_scripted_profiles() -> None:
    for profile in ("deterministic", "scripted-model"):
        cases = get_manifest("internal-core", profile, 7)
        result = asyncio.run(run_suite("internal-core", profile, cases, 7))
        assert result.acceptance.accepted
        assert [item.executions for item in result.cases[:4]] == [1, 1, 1, 1]
        assert result.cases[3].page_request_count == 1
        assert result.cases[4].executions == 2


def test_internal_core_local_http_model_policy_profile() -> None:
    profile = "local-http-model-policy"
    result = asyncio.run(run_suite("internal-core", profile, get_manifest("internal-core", profile, 7), 7))
    assert result.acceptance.accepted
    assert [item.provider_attempts for item in result.cases] == [1, 1, 1]
