from affordance_runtime.benchmarks.external_smoke.live_reporting import write_fixed_external_smoke
from affordance_runtime.benchmarks.external_smoke.live_runner import FixedExternalSmokeOutcome
from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    MetricMeasurement,
    TerminalReasonCode,
)


def test_live_report_is_private_and_attestation_is_exact(tmp_path) -> None:
    safety = {
        name: MetricMeasurement(0, True)
        for name in (
            "sent_unknown_count", "duplicate_unknown_attempts", "forbidden_effect_attempts",
            "stale_zero_call_violations", "provider_retry_count", "fallback_count", "cleanup_failures",
        )
    }
    identity = BenchmarkRunIdentity(
        "run:opaque", "a" * 40, False, "browsergym-fixed-external-smoke",
        "digest", "mistral-format-only-mechanical", 7, "2026-08-09T00:00:00+00:00",
        "3.12", "linux",
    )
    case = BenchmarkCaseResult("miniwob-click-button", "done", True, "", 1.0, safety)
    suite = BenchmarkSuiteResult(identity, (case,), BenchmarkAcceptance(True, ()), {})
    outcome = FixedExternalSmokeOutcome(
        suite, True, (), "mistral", "mistral-medium-3-5", "format-only.v1", 7.5,
    )
    write_fixed_external_smoke(outcome, tmp_path)
    report = (tmp_path / "external-smoke-report.json").read_text().casefold()
    attestation = (tmp_path / "attestation.json").read_text()
    for item in EXTERNAL_SMOKE_MANIFEST.cases:
        assert item.benchmark_task_id.casefold() not in report
    for marker in (
        "raw_response", "raw_prompt", "chain_of_thought", "selector", "private_element_id",
        "coordinate", "href", "expected_answer", "hidden_state", "raw_reward", "credential",
        "endpoint_url", "reference_action",
    ):
        assert marker not in report
    assert '"schema_version": "external-smoke-report.v2"' in report
    assert '"accepted": true' in attestation.lower()
    assert '"git_dirty": false' in attestation.lower()
    assert "mistral-medium-3-5" in attestation


def test_blocked_live_report_contains_only_bounded_terminal_reason(tmp_path) -> None:
    safety = {
        name: MetricMeasurement(0, True)
        for name in (
            "sent_unknown_count", "duplicate_unknown_attempts", "forbidden_effect_attempts",
            "stale_zero_call_violations", "provider_retry_count", "fallback_count",
            "cleanup_failures",
        )
    }
    identity = BenchmarkRunIdentity(
        "run:opaque", "a" * 40, False, "browsergym-fixed-external-smoke",
        "digest", "mistral-format-only-mechanical", 7, "2026-08-09T00:00:00+00:00",
        "3.12", "linux",
    )
    case = BenchmarkCaseResult(
        "miniwob-choose-list", "blocked", True, "", 1.0, safety,
        TerminalReasonCode.ACTION_OUTSIDE_CURRENT_PAGE,
    )
    suite = BenchmarkSuiteResult(
        identity, (case,), BenchmarkAcceptance(False, ("case blocked",)), {},
    )
    outcome = FixedExternalSmokeOutcome(
        suite, False, ("case blocked",), "mistral", "mistral-medium-3-5",
        "format-only.v1", 7.5,
    )

    write_fixed_external_smoke(outcome, tmp_path)

    report = (tmp_path / "external-smoke-report.json").read_text().casefold()
    assert '"terminal_reason_code": "action_outside_current_page"' in report
    assert "private-action-id" not in report
