import json
import threading
from pathlib import Path
from types import SimpleNamespace

from affordance_runtime.benchmarks.local import LocalSaasRunCase
from affordance_runtime.benchmarks.suites import mvp_benchmark_tasks
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.fixtures import create_fixture_server


def test_recovery_success_count_uses_recorded_outcomes() -> None:
    nodes = [
        SimpleNamespace(kind="RecoveryOutcomeRecorded", payload={"outcome": {"success": True}}),
        SimpleNamespace(kind="RecoveryOutcomeRecorded", payload={"outcome": {"success": False}}),
        SimpleNamespace(kind="TaskCompleted", payload={}),
    ]

    assert LocalSaasRunCase._successful_recovery_outcomes(nodes) == 1


def test_settings_recovery_blocks_stale_dispatch_then_retries_verified_absence(tmp_path: Path) -> None:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        task = next(item for item in mvp_benchmark_tasks() if item.task_id == "reversible_settings_update")
        run = LocalSaasRunCase(base_url, tmp_path / "artifacts").run_runtime_case(
            task,
            "full_runtime",
            0,
            RuntimeFeatures(),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    events = [json.loads(line) for line in Path(run.trace_path).read_text(encoding="utf-8").splitlines()]
    event_types = [item["event_type"] for item in events]
    settlements = [
        item["payload"]["status"]
        for item in events
        if item["event_type"] == "EffectSettled"
    ]

    assert run.success
    assert run.stale_actions_blocked == 1
    assert run.recovery_attempts == run.recovery_successes == 2
    assert event_types.count("EnvironmentDriftDetected") == 1
    assert event_types.count("RecoveryStateInspected") == 1
    assert settlements == ["not_occurred", "occurred"]
    assert "UncertainExternalEffectRecorded" not in event_types


def test_containment_profiles_record_expected_trace_failures(tmp_path: Path) -> None:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        tasks = {item.task_id: item for item in mvp_benchmark_tasks()}
        run_case = LocalSaasRunCase(base_url, tmp_path / "artifacts")
        probes = (
            run_case.run_runtime_case(
                tasks["read_only_evidence_chain"],
                "no_structural_verifier",
                0,
                RuntimeFeatures(structural_verification=False),
            ),
            run_case.run_runtime_case(
                tasks["export_with_approval"],
                "no_capability_gate",
                0,
                RuntimeFeatures(capability_gate=False),
            ),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert [run.failure_reason for run in probes] == [
        "expected:verification_failed",
        "expected:capability_denied",
    ]
    assert all(not run.success and Path(run.trace_path).is_file() for run in probes)


def test_export_oracle_requires_the_typed_download_artifact(tmp_path: Path) -> None:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        task = next(item for item in mvp_benchmark_tasks() if item.task_id == "export_with_approval")
        run = LocalSaasRunCase(base_url, tmp_path / "artifacts").run_runtime_case(
            task,
            "full_runtime",
            0,
            RuntimeFeatures(),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    downloads = tuple((tmp_path / "artifacts" / "runs").glob("*/downloads/report.csv"))
    assert run.success
    assert len(downloads) == 1
