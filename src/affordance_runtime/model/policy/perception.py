"""Model-facing perception profile shared by both decision adapters."""

from __future__ import annotations

from enum import StrEnum

from affordance_runtime.model.policy.contracts import ModelDecisionRequest

_RAW_VISUAL_PURPOSES = frozenset({"visual_property", "text_in_image"})


class DecisionPerceptionProfile(StrEnum):
    TEXT_ONLY = "text-only.v1"
    SCREENSHOT_AX = "screenshot-ax.v1"
    STRUCTURE_FIRST = "structure-first.v1"


def perception_uses_images(
    request: ModelDecisionRequest,
    profile: DecisionPerceptionProfile,
) -> bool:
    if profile is DecisionPerceptionProfile.TEXT_ONLY:
        return False
    if profile is DecisionPerceptionProfile.SCREENSHOT_AX:
        return True
    context = request.agent_context
    if context is None or not context.recent_steps.items:
        return False
    latest = context.recent_steps.items[-1]
    if (
        latest.decision_kind != "requestobservation"
        or latest.semantic_summary.get("purpose") not in _RAW_VISUAL_PURPOSES
        or latest.semantic_summary.get("feedback_code") != "observation_acquired"
    ):
        return False
    return any(
        source.modality == "visual"
        and source.freshness == "current"
        and (
            source.projection_coverage != "complete"
            or source.conflict_status != "clear"
        )
        for source in context.actor_world.sources
    )
