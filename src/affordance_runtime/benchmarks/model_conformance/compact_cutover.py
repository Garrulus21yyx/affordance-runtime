"""Pure readiness evaluation for a future compact-v2 default change."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.model.policy.grounding import MAX_COMPACT_GUIDE_BYTES


@dataclass(frozen=True)
class CompactDefaultCutoverEvidence:
    v2_contract_frozen: bool
    v2_schema_runtime_consistent: bool
    v2_guide_privacy_passed: bool
    qwen_full_recurrent_supported: bool
    llama_full_recurrent_supported: bool
    seven_decision_runtime_matrix_passed: bool
    multi_action_matrix_passed: bool
    destination_matrix_passed: bool
    first_action_bias_detected: bool
    strong_provider_no_regression: bool | None
    strong_provider_samples_sufficient: bool
    parser_changed: bool
    runtime_admission_changed: bool
    retry_or_fallback_added: bool
    private_route_leakage: bool
    full_regression_passed: bool
    exact_head_ci_available: bool
    compact_guide_bytes: int

    def __post_init__(self) -> None:
        if self.compact_guide_bytes < 0:
            raise ValueError("compact guide measurement must be nonnegative")


@dataclass(frozen=True)
class CompactDefaultCutoverReadiness:
    admitted: bool
    errors: tuple[str, ...]


def evaluate_compact_default_cutover(
    evidence: CompactDefaultCutoverEvidence,
) -> CompactDefaultCutoverReadiness:
    checks = (
        (evidence.v2_contract_frozen, "compact-contract.v2 guide contract is not frozen"),
        (evidence.v2_schema_runtime_consistent, "v2 schema/runtime limits or digest are inconsistent"),
        (evidence.v2_guide_privacy_passed, "v2 guide privacy did not pass"),
        (evidence.qwen_full_recurrent_supported, "Qwen exact v2 full recurrent policy is not supported"),
        (evidence.llama_full_recurrent_supported, "Llama exact v2 full recurrent policy is not supported"),
        (evidence.seven_decision_runtime_matrix_passed, "seven-decision Runtime matrix is not closed"),
        (evidence.multi_action_matrix_passed, "multi-action matrix is not closed"),
        (evidence.destination_matrix_passed, "destination matrix is not closed"),
        (not evidence.first_action_bias_detected, "first-action bias was detected"),
        (evidence.strong_provider_no_regression is True, "strong-provider semantic no-regression is unavailable or failed"),
        (evidence.strong_provider_samples_sufficient, "strong-provider availability samples are insufficient"),
        (not evidence.parser_changed, "canonical parser changed"),
        (not evidence.runtime_admission_changed, "Runtime admission changed"),
        (not evidence.retry_or_fallback_added, "retry or fallback was added"),
        (not evidence.private_route_leakage, "compact projection leaked private route data"),
        (evidence.full_regression_passed, "full regression suite did not pass"),
        (evidence.exact_head_ci_available, "exact-head remote CI is unavailable"),
        (evidence.compact_guide_bytes <= MAX_COMPACT_GUIDE_BYTES, "compact guide exceeds 4 KiB"),
    )
    errors = tuple(message for passed, message in checks if not passed)
    return CompactDefaultCutoverReadiness(not errors, errors)
