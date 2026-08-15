import asyncio
from dataclasses import replace

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.reporting import write_run_report
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_serialized_report_omits_environment_policy_and_private_sentinels(tmp_path) -> None:
    sentinels = (
        "selector-SENTINEL", "coordinate-SENTINEL", "https://private.invalid/SENTINEL",
        "credential-SENTINEL", "Authorization-SENTINEL", "raw-response-SENTINEL",
        "/private/artifact-SENTINEL", "artifact-value-SENTINEL",
    )
    manifest = get_manifest("internal-core", "deterministic", 7)
    original = manifest.cases[0]

    def environment(instrumentation):
        value = original.environment_factory(instrumentation)
        value.private_sentinels = sentinels
        return value

    def composition(instrumentation):
        value = original.composition_factory(instrumentation)
        value.policy.private_provider_payload = sentinels
        return value

    case = replace(original, environment_factory=environment, composition_factory=composition)
    result = asyncio.run(run_suite(replace(manifest, cases=(case,))))
    write_run_report(result, str(tmp_path))

    serialized = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json"))
    assert result.acceptance.accepted
    assert '"runtime": "core"' in serialized
    assert all(sentinel not in serialized for sentinel in sentinels)
