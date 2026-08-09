import sys

from affordance_runtime.benchmarks.external_smoke import cli
from affordance_runtime.benchmarks.external_smoke.contracts import ExternalBenchmarkAdmission


def test_fixed_live_runner_builds_no_provider_before_all_gates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "build_external_admission_evidence", lambda *_args: object())
    monkeypatch.setattr(cli, "evaluate_external_admission", lambda *_args: ExternalBenchmarkAdmission(True, ()))
    monkeypatch.setattr(cli, "write_preflight_report", lambda *_args: None)
    monkeypatch.delenv("RUN_EXTERNAL_SMOKE", raising=False)

    def forbidden_policy(*_args, **_kwargs):
        raise AssertionError("provider must not be constructed before explicit environment opt-in")

    monkeypatch.setattr(cli, "model_policy_from_environment", forbidden_policy)
    monkeypatch.setattr(sys, "argv", [
        "external-smoke", "run", "--manifest", "external-smoke-v1",
        "--profile", "mistral-format-only-mechanical",
        "--internal-attestation", "internal.json", "--full-ci-attestation", "full.json",
        "--live-policy-attestation", "live.json", "--adapter-attestation", "adapter.json",
        "--execute", "--output-dir", str(tmp_path),
    ])
    assert cli.main() == 1


def test_external_pacing_module_is_absent_from_agent_loop_and_model_policy() -> None:
    from pathlib import Path

    for root in (Path("src/affordance_runtime/agent"), Path("src/affordance_runtime/model_policy")):
        assert all("external_smoke.pacing" not in path.read_text() for path in root.rglob("*.py"))
