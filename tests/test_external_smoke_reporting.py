from affordance_runtime.benchmarks.external_smoke.contracts import (
    ExternalBenchmarkAdmission,
    ExternalBenchmarkAdmissionEvidence,
    ExternalSmokeExecution,
)
from affordance_runtime.benchmarks.external_smoke.reporting import write_preflight_report


def test_external_report_excludes_oracle_route_and_credential_text(tmp_path) -> None:
    output = tmp_path / "preflight.json"
    write_preflight_report(
        output,
        ExternalBenchmarkAdmissionEvidence(
            *("a" * 40 for _ in range(4)), *("sha256:" + "1" * 64 for _ in range(4)),
            True, True, True, True, False, None, 0, 0, 0, True, False, "", False,
        ),
        ExternalBenchmarkAdmission(False, ("live policy unavailable",)),
        ExternalSmokeExecution(False, "not_run", ()),
    )
    text = output.read_text().lower()
    for forbidden in (
        "expected_answer", "hidden_state", "selector", "coordinate", "authorization", "api_key",
    ):
        assert forbidden not in text
