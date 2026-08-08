import json

from affordance_runtime.benchmarks.external_smoke.cli import (
    EXPECTED_INTERNAL_PROFILES,
    build_external_admission_evidence,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalDependencyStatus


def test_preflight_builds_exact_secret_free_evidence(monkeypatch, tmp_path) -> None:
    sha = "a" * 40
    internal = tmp_path / "internal.json"
    internal.write_text(json.dumps({
        "git_sha": sha, "accepted": True,
        "run_profiles": sorted(EXPECTED_INTERNAL_PROFILES),
        "forbidden_effect_attempts": 0,
        "duplicate_unknown_attempts": 0,
        "stale_zero_call_violations": 0,
    }))
    full = tmp_path / "full.json"
    full.write_text(json.dumps({"git_sha": sha, "accepted": True}))
    live = tmp_path / "live.json"
    live.write_text(json.dumps({"git_sha": sha, "accepted": False, "status": "unavailable"}))
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_smoke.cli._git",
        lambda *args: sha if args[:2] == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_smoke.cli.external_dependency_status",
        lambda: ExternalDependencyStatus(False, "browsergym-miniwob", "", False),
    )

    evidence = build_external_admission_evidence(internal, full, live)

    assert evidence.git_sha == sha and evidence.clean_tree
    assert not evidence.live_policy_accepted
    assert not evidence.optional_dependency_available
    assert evidence.expected_internal_run_set_complete
    assert evidence.internal_harness_attestation_sha256.startswith("sha256:")


def test_preflight_missing_attestations_fail_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_smoke.cli._git",
        lambda *args: "a" * 40 if args[:2] == ("rev-parse", "HEAD") else "",
    )
    evidence = build_external_admission_evidence(
        tmp_path / "missing-internal", tmp_path / "missing-full", tmp_path / "missing-live",
    )
    assert not evidence.internal_harness_accepted
    assert not evidence.full_ci_accepted and not evidence.live_policy_accepted
    assert evidence.forbidden_effect_attempts == -1
