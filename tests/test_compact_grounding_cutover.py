from dataclasses import replace

from affordance_runtime.benchmarks.model_conformance.compact_cutover import (
    CompactDefaultCutoverEvidence,
    evaluate_compact_default_cutover,
)


def _evidence() -> CompactDefaultCutoverEvidence:
    return CompactDefaultCutoverEvidence(
        v2_contract_frozen=True,
        v2_schema_runtime_consistent=True,
        v2_guide_privacy_passed=True,
        qwen_full_recurrent_supported=True,
        llama_full_recurrent_supported=True,
        seven_decision_runtime_matrix_passed=True,
        multi_action_matrix_passed=True,
        destination_matrix_passed=True,
        first_action_bias_detected=False,
        strong_provider_no_regression=True,
        strong_provider_samples_sufficient=True,
        parser_changed=False,
        runtime_admission_changed=False,
        retry_or_fallback_added=False,
        private_route_leakage=False,
        full_regression_passed=True,
        exact_head_ci_available=True,
        compact_guide_bytes=4_031,
    )


def test_complete_evidence_admits_only_a_future_default_commit() -> None:
    result = evaluate_compact_default_cutover(_evidence())
    assert result.admitted and result.errors == ()


def test_actual_m35_profile_failures_and_provider_unavailability_block() -> None:
    result = evaluate_compact_default_cutover(replace(
        _evidence(),
        qwen_full_recurrent_supported=False,
        llama_full_recurrent_supported=False,
        strong_provider_no_regression=None,
        strong_provider_samples_sufficient=False,
        exact_head_ci_available=False,
    ))
    assert not result.admitted
    assert any("Qwen" in error for error in result.errors)
    assert any("Llama" in error for error in result.errors)
    assert any("strong-provider" in error for error in result.errors)
    assert any("remote CI" in error for error in result.errors)


def test_bias_runtime_matrix_or_oversized_guide_blocks() -> None:
    result = evaluate_compact_default_cutover(replace(
        _evidence(), seven_decision_runtime_matrix_passed=False,
        first_action_bias_detected=True, compact_guide_bytes=4_097,
    ))
    assert not result.admitted and len(result.errors) == 3
