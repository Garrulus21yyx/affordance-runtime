"""Pure readiness evaluation for a future compact-grounding default change."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.model_policy.grounding import MAX_COMPACT_GUIDE_BYTES


@dataclass(frozen=True)
class CompactDefaultCutoverEvidence:
    schema_runtime_consistent: bool
    exact_local_profiles_supported: bool
    seven_decision_matrix_passed: bool
    multi_action_matrix_passed: bool
    destination_matrix_passed: bool
    first_action_bias_detected: bool
    private_route_leakage: bool
    runtime_admission_changed: bool
    parser_changed: bool
    retry_or_fallback_added: bool
    strong_provider_no_regression: bool | None
    full_regression_passed: bool
    exact_head_ci_available: bool
    compact_prompt_delta_bytes: int
    compact_prompt_token_delta: int | None
    compact_guide_bytes: int

    def __post_init__(self) -> None:
        if self.compact_prompt_delta_bytes < 0 or self.compact_guide_bytes < 0:
            raise ValueError("compact prompt measurements must be nonnegative")
        if self.compact_prompt_token_delta is not None and self.compact_prompt_token_delta < 0:
            raise ValueError("compact prompt token delta must be nonnegative")


@dataclass(frozen=True)
class CompactDefaultCutoverReadiness:
    admitted: bool
    errors: tuple[str, ...]


def evaluate_compact_default_cutover(
    evidence: CompactDefaultCutoverEvidence,
) -> CompactDefaultCutoverReadiness:
    checks = (
        (evidence.schema_runtime_consistent, "schema/runtime limits or digest are inconsistent"),
        (evidence.exact_local_profiles_supported, "exact local compact profiles are not supported"),
        (evidence.seven_decision_matrix_passed, "seven-decision matrix is not closed"),
        (evidence.multi_action_matrix_passed, "multi-action matrix is not closed"),
        (evidence.destination_matrix_passed, "destination matrix is not closed"),
        (not evidence.first_action_bias_detected, "first-action bias was detected"),
        (not evidence.private_route_leakage, "compact projection leaked private route data"),
        (not evidence.runtime_admission_changed, "Runtime admission changed"),
        (not evidence.parser_changed, "canonical parser changed"),
        (not evidence.retry_or_fallback_added, "retry or fallback was added"),
        (evidence.strong_provider_no_regression is True, "strong-provider no-regression is unavailable or failed"),
        (evidence.full_regression_passed, "full regression suite did not pass"),
        (evidence.exact_head_ci_available, "exact-head remote CI is unavailable"),
        (evidence.compact_guide_bytes <= MAX_COMPACT_GUIDE_BYTES, "compact guide exceeds 4 KiB"),
    )
    errors = tuple(message for passed, message in checks if not passed)
    return CompactDefaultCutoverReadiness(not errors, errors)
