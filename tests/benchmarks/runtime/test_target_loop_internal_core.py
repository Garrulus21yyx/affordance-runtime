import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_internal_core_deterministic_and_scripted_profiles() -> None:
    for profile in ("deterministic", "scripted-model"):
        manifest = get_manifest("internal-core", profile, 7)
        result = asyncio.run(run_suite(manifest))
        assert result.acceptance.accepted
        assert [item.measurements["executions"].value for item in result.cases[:4]] == [1, 1, 1, 1]
        assert result.cases[3].measurements["page_request_count"].value == 1
        assert result.cases[4].measurements["executions"].value == 2


def test_internal_core_local_http_model_policy_profile() -> None:
    profile = "local-http-model-policy"
    result = asyncio.run(run_suite(get_manifest("internal-core", profile, 7)))
    assert result.acceptance.accepted
    assert [item.measurements["provider_attempts"].value for item in result.cases] == [1, 1, 1]
