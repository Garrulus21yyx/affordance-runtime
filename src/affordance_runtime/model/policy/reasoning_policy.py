"""Mechanical role-budget selection for the single ActionPolicy role."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.observation_delivery import InformationDeltaKind
from affordance_runtime.agent.decisions import ReadRegionResult

_COLLECTION_SCOPE_ROLES = frozenset({"feed", "grid", "list", "table", "tree"})
_EVIDENCE_REVIEW_MAX_TOKENS = 2048


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
    EVIDENCE_REVIEW = "evidence_review"
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
    deliberate_max_tokens: int = 4096
    repair_max_tokens: int = 512

    def __post_init__(self) -> None:
        if not 512 <= self.ordinary_max_tokens <= 1024:
            raise ValueError("ordinary ActionPolicy cap must be within [512, 1024]")
        if not 1024 <= self.deliberate_max_tokens <= 4096:
            raise ValueError("deliberate ActionPolicy cap must be within [1024, 4096]")
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
                "disabled",
            )
        if _at_collection_evidence_boundary(context):
            return ActionPolicyCallProfile(
                ActionPolicyInvocationPhase.DELIBERATE,
                ActionPolicyInvocationTrigger.EVIDENCE_REVIEW,
                min(self.deliberate_max_tokens, _EVIDENCE_REVIEW_MAX_TOKENS),
                "disabled",
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


def _at_collection_evidence_boundary(context: AgentContext) -> bool:
    """Lease one bounded audit only for a newly extended collection inventory."""

    last_step = context.last_step
    decision = getattr(last_step, "decision", None)
    if not isinstance(decision, ReadRegionResult):
        return False
    recent_steps = context.workspace.recent_steps
    if not recent_steps:
        return False
    recent = recent_steps[-1]
    if (
        recent.semantic_action != "read_region"
        or recent.semantic_summary.get("information_delta")
        != InformationDeltaKind.NEW_INFORMATION.value
    ):
        return False
    result = decision.result
    scope = result.get("scope")
    items = result.get("items")
    return bool(
        result.get("kind") == "Opened"
        and result.get("has_more") is False
        and result.get("source_coverage") in {"complete", "partial"}
        and result.get("region_membership") in {"complete", "partial"}
        and isinstance(scope, Mapping)
        and str(scope.get("role", "")).casefold() in _COLLECTION_SCOPE_ROLES
        and isinstance(items, tuple | list)
        and any(isinstance(item, Mapping) and item.get("kind") in {"complete_item", "partial_item"} for item in items)
    )
