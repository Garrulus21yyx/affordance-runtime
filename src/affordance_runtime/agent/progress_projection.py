"""Bounded route-free projection of verified run progress."""

from __future__ import annotations

from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.context import AgentProgressEventView

_MAX_PROGRESS_EVENTS = 3


def project_progress_events(state) -> BoundedSection[AgentProgressEventView]:
    events = state.recent_progress_events[-_MAX_PROGRESS_EVENTS:]
    items = tuple(
        AgentProgressEventView(
            item.event_type,
            item.semantic_action,
            item.target_id,
            item.attempt_key_digest,
            item.effect_status,
            item.task_status,
            item.strategy_transition_required,
        )
        for item in events
    )
    total = state.progress_event_total_count
    return BoundedSection(items, total, total > len(items))
