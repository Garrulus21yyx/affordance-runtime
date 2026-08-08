from dataclasses import replace

from affordance_runtime.benchmarks.external_smoke.admission import evaluate_external_admission
from affordance_runtime.benchmarks.external_smoke.contracts import ExternalBenchmarkAdmissionEvidence
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    external_manifest_digest,
)


def _evidence(**changes) -> ExternalBenchmarkAdmissionEvidence:
    sha = "a" * 40
    values = dict(
        git_sha=sha, internal_git_sha=sha, full_ci_git_sha=sha, live_policy_git_sha=sha,
        internal_harness_attestation_sha256="sha256:" + "1" * 64,
        full_ci_attestation_sha256="sha256:" + "2" * 64,
        live_model_policy_attestation_sha256="sha256:" + "3" * 64,
        external_manifest_digest=external_manifest_digest(EXTERNAL_SMOKE_MANIFEST),
        internal_harness_accepted=True, expected_internal_run_set_complete=True,
        full_ci_accepted=True, live_policy_accepted=True,
        live_evaluator_required=False, live_evaluator_accepted=None,
        forbidden_effect_attempts=0, duplicate_unknown_attempts=0,
        stale_zero_call_violations=0, clean_tree=True,
        optional_dependency_available=True, optional_dependency_version="0.14.3",
        target_loop_adapter_ready=True,
    )
    values.update(changes)
    return ExternalBenchmarkAdmissionEvidence(**values)


def test_external_admission_accepts_only_the_complete_exact_gate() -> None:
    assert evaluate_external_admission(_evidence(), EXTERNAL_SMOKE_MANIFEST).admitted
    assert not evaluate_external_admission(
        _evidence(live_policy_accepted=False), EXTERNAL_SMOKE_MANIFEST,
    ).admitted
    assert not evaluate_external_admission(
        _evidence(full_ci_git_sha="b" * 40), EXTERNAL_SMOKE_MANIFEST,
    ).admitted
    assert not evaluate_external_admission(
        _evidence(clean_tree=False), EXTERNAL_SMOKE_MANIFEST,
    ).admitted
    assert not evaluate_external_admission(
        _evidence(target_loop_adapter_ready=False), EXTERNAL_SMOKE_MANIFEST,
    ).admitted


def test_mechanical_manifest_does_not_require_live_semantic_evaluator() -> None:
    assert evaluate_external_admission(_evidence(), EXTERNAL_SMOKE_MANIFEST).admitted
    semantic = replace(EXTERNAL_SMOKE_MANIFEST, mechanical_only=False)
    result = evaluate_external_admission(
        _evidence(
            external_manifest_digest=external_manifest_digest(semantic),
            live_evaluator_required=True,
        ),
        semantic,
    )
    assert not result.admitted
    assert any("semantic evaluator" in item for item in result.errors)


def test_external_admission_rejects_manifest_digest_and_safety_mismatch() -> None:
    assert not evaluate_external_admission(
        _evidence(external_manifest_digest="sha256:" + "0" * 64), EXTERNAL_SMOKE_MANIFEST,
    ).admitted
    assert not evaluate_external_admission(
        _evidence(duplicate_unknown_attempts=1), EXTERNAL_SMOKE_MANIFEST,
    ).admitted
