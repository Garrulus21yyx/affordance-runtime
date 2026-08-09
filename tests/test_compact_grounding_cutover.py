from dataclasses import replace

from affordance_runtime.benchmarks.model_conformance.compact_cutover import (
    CompactDefaultCutoverEvidence,
    evaluate_compact_default_cutover,
)


def _evidence() -> CompactDefaultCutoverEvidence:
    return CompactDefaultCutoverEvidence(
        schema_runtime_consistent=True,
        exact_local_profiles_supported=True,
        seven_decision_matrix_passed=True,
        multi_action_matrix_passed=True,
        destination_matrix_passed=True,
        first_action_bias_detected=False,
        private_route_leakage=False,
        runtime_admission_changed=False,
        parser_changed=False,
        retry_or_fallback_added=False,
        strong_provider_no_regression=True,
        full_regression_passed=True,
        exact_head_ci_available=True,
        compact_prompt_delta_bytes=800,
        compact_prompt_token_delta=200,
        compact_guide_bytes=3_900,
    )


def test_complete_evidence_admits_only_a_future_default_commit() -> None:
    result = evaluate_compact_default_cutover(_evidence())
    assert result.admitted
    assert result.errors == ()


def test_missing_strong_provider_or_exact_head_ci_blocks() -> None:
    result = evaluate_compact_default_cutover(replace(
        _evidence(), strong_provider_no_regression=None, exact_head_ci_available=False,
    ))
    assert not result.admitted
    assert any("strong-provider" in error for error in result.errors)
    assert any("remote CI" in error for error in result.errors)


def test_bias_matrix_or_oversized_guide_blocks() -> None:
    result = evaluate_compact_default_cutover(replace(
        _evidence(),
        seven_decision_matrix_passed=False,
        first_action_bias_detected=True,
        compact_guide_bytes=4_097,
    ))
    assert not result.admitted
    assert len(result.errors) == 3
