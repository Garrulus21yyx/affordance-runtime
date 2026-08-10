"""Canonical target-loop metric namespace and collision validation."""

from __future__ import annotations

CANONICAL_METRICS = frozenset({
    "observations", "executions", "currentness_probes", "turns",
    "policy_calls", "semantic_judge_calls", "provider_attempts",
    "confirmations", "sent_unknown_count", "duplicate_unknown_attempts",
    "forbidden_effect_attempts", "stale_opportunities",
    "stale_zero_call_violations", "effectful_dispatches",
    "reset_acquisitions", "independent_capture_calls",
    "post_action_acquisitions", "provider_retry_count", "prompt_tokens",
    "completion_tokens", "total_tokens", "model_latency_ms",
    "ask_user_count", "wait_count", "page_request_count", "cleanup_failures",
})


def canonical_metric_collisions(names) -> tuple[str, ...]:
    """Return deterministic canonical/custom collisions without mutating inputs."""
    return tuple(sorted(CANONICAL_METRICS.intersection(names)))


def require_custom_metric_name(name: str) -> None:
    if name in CANONICAL_METRICS:
        raise ValueError("custom metric cannot override a canonical metric")
