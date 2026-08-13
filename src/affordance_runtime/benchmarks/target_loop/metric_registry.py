"""Canonical target-loop metric namespace and collision validation."""

from __future__ import annotations

CANONICAL_METRICS = frozenset(
    {
        "observations",
        "executions",
        "currentness_probes",
        "turns",
        "policy_calls",
        "policy_schema_repair_count",
        "tool_argument_repair_count",
        "valid_tool_call_count",
        "admitted_decision_count",
        "zero_tool_call_count",
        "multiple_tool_call_count",
        "unknown_tool_call_count",
        "invalid_tool_argument_count",
        "stale_tool_catalog_count",
        "tool_grounding_gap_count",
        "tool_catalog_count",
        "tool_catalog_bytes",
        "semantic_judge_calls",
        "provider_attempts",
        "confirmations",
        "sent_unknown_count",
        "duplicate_unknown_attempts",
        "forbidden_effect_attempts",
        "stale_opportunities",
        "stale_zero_call_violations",
        "effectful_dispatches",
        "reset_acquisitions",
        "independent_capture_calls",
        "post_action_acquisitions",
        "provider_retry_count",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "model_latency_ms",
        "ask_user_count",
        "wait_count",
        "page_request_count",
        "cleanup_failures",
        "observation_contract_exceptions",
        "feedback_repairable_rejection_count",
        "feedback_no_information_gain_count",
        "feedback_strategy_transition_required_count",
        "feedback_action_admission_source_count",
        "feedback_action_page_source_count",
        "feedback_policy_observation_source_count",
        "feedback_action_evaluation_source_count",
        "feedback_progress_event_source_count",
        "feedback_context_delivery_count",
        "feedback_related_decision_snapshot_count",
        "feedback_contract_violation_snapshot_count",
        "feedback_semantic_effect_snapshot_count",
        "feedback_recovery_constraints_count",
        "control_issue_budget_consumption_count",
        "control_repetition_termination_count",
        "first_opportunity_policy_decision_count",
        "first_opportunity_admission_corrected_count",
        "second_opportunity_policy_decision_count",
        "second_opportunity_admission_corrected_count",
        "strategy_transition_feedback_count",
        "first_policy_repair_feedback_count",
        "repair_feedback_zero_call_violation_count",
        "feedback_invalid_action_parameters_code_count",
        "feedback_action_outside_action_space_code_count",
        "feedback_action_outside_current_page_code_count",
        "feedback_destination_outside_current_page_code_count",
        "feedback_action_page_no_information_gain_code_count",
        "feedback_observation_no_information_gain_code_count",
    }
)


def canonical_metric_collisions(names) -> tuple[str, ...]:
    """Return deterministic canonical/custom collisions without mutating inputs."""
    return tuple(sorted(CANONICAL_METRICS.intersection(names)))


def require_custom_metric_name(name: str) -> None:
    if name in CANONICAL_METRICS:
        raise ValueError("custom metric cannot override a canonical metric")
