"""Mechanical role-budget selection for the single ActionPolicy role."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.context.context import AgentContext


class ActionPolicyInvocationPhase(StrEnum):
    ORDINARY = "ordinary"
    DELIBERATE = "deliberate"
    REPRESENTATION_REPAIR = "representation_repair"


class ActionPolicyInvocationTrigger(StrEnum):
    ORDINARY = "ordinary"
    GROUNDING_GAP = "grounding_gap"
    EVIDENCE_GAP = "evidence_gap"
    OPERATIONAL_STALL = "operational_stall"
    CONTROL_STALL = "control_stall"
    REPRESENTATION_ERROR = "representation_error"


@dataclass(frozen=True)
class ActionPolicyCallProfile:
    phase: ActionPolicyInvocationPhase
    trigger: ActionPolicyInvocationTrigger
    max_output_tokens: int
    thinking_mode: str


@dataclass(frozen=True)
class ActionPolicyReasoningPolicy:
    ordinary_max_tokens: int = 1024
    deliberate_max_tokens: int = 2048
    repair_max_tokens: int = 512

    def __post_init__(self) -> None:
        if not 512 <= self.ordinary_max_tokens <= 1024:
            raise ValueError("ordinary ActionPolicy cap must be within [512, 1024]")
        if not 1024 <= self.deliberate_max_tokens <= 2048:
            raise ValueError("deliberate ActionPolicy cap must be within [1024, 2048]")
        if not 256 <= self.repair_max_tokens <= 512:
            raise ValueError("representation repair cap must be within [256, 512]")

    def select(self, context: AgentContext) -> ActionPolicyCallProfile:
        feedback = context.control_feedback
        signature = str(feedback.get("stable_signature", ""))
        trigger = _deliberate_trigger(str(feedback.get("kind", "")))
        if signature and trigger is not None:
            return ActionPolicyCallProfile(
                ActionPolicyInvocationPhase.DELIBERATE,
                trigger,
                self.deliberate_max_tokens,
                "enabled",
            )
        return ActionPolicyCallProfile(
            ActionPolicyInvocationPhase.ORDINARY,
            ActionPolicyInvocationTrigger.ORDINARY,
            self.ordinary_max_tokens,
            "disabled",
        )

    def repair(self) -> ActionPolicyCallProfile:
        return ActionPolicyCallProfile(
            ActionPolicyInvocationPhase.REPRESENTATION_REPAIR,
            ActionPolicyInvocationTrigger.REPRESENTATION_ERROR,
            self.repair_max_tokens,
            "disabled",
        )


def _deliberate_trigger(kind: str) -> ActionPolicyInvocationTrigger | None:
    if kind == "grounding_stall":
        return ActionPolicyInvocationTrigger.GROUNDING_GAP
    if kind in {"capability_gap"}:
        return ActionPolicyInvocationTrigger.EVIDENCE_GAP
    if kind == "control_stall":
        return ActionPolicyInvocationTrigger.CONTROL_STALL
    if kind in {"effect_stall", "uncertain_effect", "state_oscillation", "strategy_review"}:
        return ActionPolicyInvocationTrigger.OPERATIONAL_STALL
    return None
