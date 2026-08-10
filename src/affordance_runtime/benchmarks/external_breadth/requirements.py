"""Bounded, policy-private MiniWoB capability requirement contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

INTERACTION_REQUIREMENTS = frozenset({
    "activate", "fill", "select", "scroll", "drag", "hover", "keypress", "clipboard",
    "multi_select", "slider", "canvas", "other", "unknown",
})
OBSERVATION_REQUIREMENTS = frozenset({
    "structural_label", "structural_role", "structural_value", "structural_selection_state",
    "structural_checked_state", "structural_relations", "table_extraction", "list_relation",
    "visual_color", "visual_geometry", "visual_spatial", "dynamic_change", "modal_state",
    "scroll_state", "multi_region", "unknown",
})
REASONING_REQUIREMENTS = frozenset({
    "direct_match", "copy", "count", "compare", "sort", "arithmetic", "text_transform",
    "stateful_game", "multi_target_sequence", "conditional_logic", "memory_across_turns",
    "unknown",
})
CONTROL_REQUIREMENTS = frozenset({
    "single_target", "form_submit", "checkbox_set", "option_select", "menu_navigation",
    "tab_navigation", "dynamic_target", "multi_step_sequence", "game_loop", "clipboard_flow",
    "unknown",
})


class TaskReadiness(StrEnum):
    DECLARED_SUPPORTED = "declared_supported"
    DECLARED_UNSUPPORTED = "declared_unsupported"
    UNASSESSED = "unassessed"


@dataclass(frozen=True)
class MiniWobTaskRequirements:
    task_id: str
    interaction_requirements: tuple[str, ...]
    observation_requirements: tuple[str, ...]
    reasoning_requirements: tuple[str, ...]
    control_requirements: tuple[str, ...]
    source_references: tuple[str, ...]
    classification_method: str
    confidence: str

    def __post_init__(self) -> None:
        axes = (
            (self.interaction_requirements, INTERACTION_REQUIREMENTS),
            (self.observation_requirements, OBSERVATION_REQUIREMENTS),
            (self.reasoning_requirements, REASONING_REQUIREMENTS),
            (self.control_requirements, CONTROL_REQUIREMENTS),
        )
        if not self.task_id or not self.source_references or not self.classification_method:
            raise ValueError("MiniWoB requirements require identity, source, and method")
        if any(not values or not set(values) <= vocabulary for values, vocabulary in axes):
            raise ValueError("MiniWoB requirements use an empty or unknown vocabulary value")
        if self.confidence not in {"high", "medium", "unassessed"}:
            raise ValueError("MiniWoB requirement confidence is invalid")


@dataclass(frozen=True)
class DeclaredAgentCapabilities:
    interaction: tuple[str, ...]
    observation: tuple[str, ...]
    reasoning: tuple[str, ...]
    control: tuple[str, ...]
