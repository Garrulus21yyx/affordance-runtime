import asyncio
from dataclasses import replace

from affordance_runtime.agent import RunStatus
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_environment_factory_failure_is_contained_and_suite_continues() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)

    def fail(_instrumentation):
        raise RuntimeError("fixture construction failed")

    failed = replace(manifest.cases[0], environment_factory=fail,
                     expected_terminal_statuses=(RunStatus.FAILED,))
    reduced = BenchmarkManifest(
        manifest.schema_version, manifest.suite_id, manifest.profile_id,
        manifest.seed, (failed, manifest.cases[1]),
    )
    result = asyncio.run(run_suite(reduced))

    assert result.cases[0].execution_completed is False
    assert "environment factory" in result.cases[0].failure_reason
    assert result.cases[1].execution_completed is True


def test_composition_failure_closes_created_environment_once() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    closed = []
    original = manifest.cases[0]

    def environment(instrumentation):
        value = original.environment_factory(instrumentation)

        async def close():
            closed.append("closed")

        value.close = close
        return value

    def composition(_instrumentation):
        raise RuntimeError("composition failed")

    case = replace(original, environment_factory=environment, composition_factory=composition,
                   expected_terminal_statuses=(RunStatus.FAILED,))
    result = asyncio.run(run_suite(BenchmarkManifest(
        manifest.schema_version, manifest.suite_id, manifest.profile_id, manifest.seed, (case,),
    )))

    assert result.cases[0].execution_completed is False
    assert "composition factory" in result.cases[0].failure_reason
    assert closed == ["closed"]
