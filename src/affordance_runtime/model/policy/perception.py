"""Model-facing perception profile shared by both decision adapters."""

from __future__ import annotations

from enum import StrEnum

from affordance_runtime.model.policy.contracts import ModelDecisionRequest


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
    if context is None:
        return False
    return any(source.modality == "visual" for source in context.world.sources)
