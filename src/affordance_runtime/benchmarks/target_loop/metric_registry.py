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
    }
)


def canonical_metric_collisions(names) -> tuple[str, ...]:
    """Return deterministic canonical/custom collisions without mutating inputs."""
    return tuple(sorted(CANONICAL_METRICS.intersection(names)))


def require_custom_metric_name(name: str) -> None:
    if name in CANONICAL_METRICS:
        raise ValueError("custom metric cannot override a canonical metric")
