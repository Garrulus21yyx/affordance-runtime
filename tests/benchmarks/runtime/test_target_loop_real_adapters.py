import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_real_dom_visual_and_wot_adapters_run_through_target_loop_harness() -> None:
    manifest = get_manifest("internal-real-adapters", "deterministic", 7)
    result = asyncio.run(run_suite(manifest))

    assert result.acceptance.accepted, result.acceptance.acceptance_errors
    assert [item.status for item in result.cases] == ["done", "done", "done"]
    dom, visual, wot = result.cases
    assert dom.measurements["dom_click_calls"].value == 1
    assert visual.measurements["visual_proposer_calls"].value == 2
    assert visual.measurements["pointer_calls"].value == 1
    assert wot.measurements["td_requests"].value == 3
    assert wot.measurements["property_reads"].value == 2
    assert wot.measurements["wot_action_calls"].value == 1


def test_synthetic_cases_are_explicitly_described_as_synthetic() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    for case in manifest.cases[:3]:
        assert "synthetic" in case.description.casefold()
