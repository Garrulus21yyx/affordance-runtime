import os

import pytest

from affordance_runtime.benchmarks.external_smoke.adapter_conformance import run_adapter_conformance

pytestmark = pytest.mark.skipif(not os.environ.get("MINIWOB_URL"), reason="fixed MiniWoB source is unavailable")


@pytest.fixture(scope="module")
def conformance():
    import asyncio

    return asyncio.run(run_adapter_conformance(7))


def test_real_click_button_adapter_conformance(conformance) -> None:
    _assert_case(conformance, "miniwob-click-button", steps=1, policy_calls=1)


def test_real_enter_text_adapter_conformance(conformance) -> None:
    case = _assert_case(conformance, "miniwob-enter-text", steps=2, policy_calls=2)
    assert case.measurements["fill_calls"].value == 1


def test_real_choose_list_adapter_conformance(conformance) -> None:
    case = _assert_case(conformance, "miniwob-choose-list", steps=2, policy_calls=2)
    assert case.measurements["select_calls"].value == 1


def test_adapter_readiness_requires_all_real_gates(conformance) -> None:
    assert conformance.accepted
    assert conformance.errors == ()
    assert conformance.target_loop_adapter_ready
    assert conformance.suite.acceptance.accepted
    assert len(conformance.suite.cases) == 3


def _assert_case(conformance, case_id: str, *, steps: int, policy_calls: int):
    case = next(item for item in conformance.suite.cases if item.case_id == case_id)
    assert case.status == "done" and case.execution_completed and not case.failure_reason
    assert case.measurements["browsergym_step_calls"].value == steps
    assert case.measurements["browsergym_probe_calls"].value == steps
    assert case.measurements["policy_calls"].value == policy_calls
    # This conformance profile is a scripted structured decision port.  It
    # exercises the product Runtime without calling an external model provider.
    assert case.measurements["provider_attempts"].value == 0
    assert case.measurements["official_success_count"].value == 1
    for name in (
        "provider_retry_count", "fallback_count", "sent_unknown_count",
        "duplicate_unknown_attempts", "forbidden_effect_attempts",
        "stale_zero_call_violations", "cleanup_failures",
    ):
        assert case.measurements[name].measured and case.measurements[name].value == 0
    return case
