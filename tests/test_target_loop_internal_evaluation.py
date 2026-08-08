import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_internal_evaluation_uses_local_http_semantic_judge() -> None:
    manifest = get_manifest("internal-evaluation", "local-http-semantic-judge", 7)
    result = asyncio.run(run_suite(manifest))
    assert result.acceptance.accepted
    assert [item.executions for item in result.cases] == [1, 1]
    assert result.cases[0].semantic_judge_calls == 1
