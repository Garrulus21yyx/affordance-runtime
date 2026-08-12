"""Pure evidence-gated visual acquisition decisions.

Provider availability is a capability, never evidence that Vision should run.
The decision consumes only the current structured observation and explicit
runtime facts; it performs no acquisition or model I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.world.contracts import SurfaceObservation


class VisionEscalationMode(StrEnum):
    SKIP = "skip"
    VERIFY_STRUCTURED_CANDIDATES = "verify_structured_candidates"
    DISCOVER_VISUAL_ENTITIES = "discover_visual_entities"
    DIAGNOSE_POSTCONDITION = "diagnose_postcondition"
    UNAVAILABLE = "unavailable"


class VisionEvidenceNeed(StrEnum):
    """The bounded kind of evidence missing from the structured control plane."""

    NONE = "none"
    OPEN_WORLD_ENTITY_DISCOVERY = "open_world_entity_discovery"
    SINGLE_TARGET_DISAMBIGUATION = "single_target_disambiguation"
    NEXT_MATCHING_TARGET = "next_matching_target"
    VISUAL_VALUE_REASONING = "visual_value_reasoning"
    POSTCONDITION_DIAGNOSIS = "postcondition_diagnosis"


@dataclass(frozen=True)
class VisionEscalationDecision:
    mode: VisionEscalationMode
    reason_code: str
    evidence_need: VisionEvidenceNeed = VisionEvidenceNeed.NONE

    @property
    def selects_visual(self) -> bool:
        return self.mode in {
            VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES,
            VisionEscalationMode.DISCOVER_VISUAL_ENTITIES,
            VisionEscalationMode.DIAGNOSE_POSTCONDITION,
        }


def decide_visual_escalation(
    structured: SurfaceObservation,
    *,
    visual_available: bool,
    candidate_verification_available: bool | None = None,
    discovery_available: bool | None = None,
    diagnosis_available: bool | None = None,
    marked_candidate_policy_available: bool = False,
    explicitly_requested: bool = False,
    terminal: bool = False,
    postcondition_unresolved: bool = False,
    task_instruction: str = "",
) -> VisionEscalationDecision:
    """Choose one current-epoch visual disposition.

    Empty structured action authority and indistinguishable actionable targets
    are concrete evidence gaps. Coverage alone is not sufficient: a truncated
    inventory may still contain the unique current action, so it must not turn
    provider presence into automatic acquisition.
    """

    if terminal:
        return VisionEscalationDecision(
            VisionEscalationMode.SKIP,
            "terminal_state_needs_no_visual",
        )

    requested_mode: VisionEscalationMode | None = None
    reason_code = "structured_evidence_sufficient"
    if explicitly_requested:
        requested_mode = VisionEscalationMode.DISCOVER_VISUAL_ENTITIES
        reason_code = "explicit_visual_observation"
        evidence_need = VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY
    elif postcondition_unresolved:
        requested_mode = VisionEscalationMode.DIAGNOSE_POSTCONDITION
        reason_code = "postcondition_visual_diagnosis"
        evidence_need = VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS
    elif not structured.bindings:
        requested_mode = VisionEscalationMode.DISCOVER_VISUAL_ENTITIES
        reason_code = "structured_action_unavailable"
        evidence_need = VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY
    elif _actionable_targets_are_ambiguous(structured):
        if _requires_visual_value_reasoning(structured, task_instruction):
            return VisionEscalationDecision(
                VisionEscalationMode.SKIP,
                "visual_value_reasoning_delegated_to_screenshot_policy",
                VisionEvidenceNeed.VISUAL_VALUE_REASONING,
            )
        if marked_candidate_policy_available:
            evidence_need = (
                VisionEvidenceNeed.NEXT_MATCHING_TARGET
                if requires_multiple_visual_targets(task_instruction)
                else VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION
            )
            return VisionEscalationDecision(
                VisionEscalationMode.SKIP,
                "marked_candidate_choice_delegated_to_screenshot_policy",
                evidence_need,
            )
        requested_mode = VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES
        if requires_multiple_visual_targets(task_instruction):
            reason_code = "next_matching_visual_target_required"
            evidence_need = VisionEvidenceNeed.NEXT_MATCHING_TARGET
        else:
            reason_code = "structured_candidates_ambiguous"
            evidence_need = VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION
    elif _requires_visual_value_reasoning(structured, task_instruction):
        return VisionEscalationDecision(
            VisionEscalationMode.SKIP,
            "visual_value_reasoning_delegated_to_screenshot_policy",
            VisionEvidenceNeed.VISUAL_VALUE_REASONING,
        )

    if requested_mode is None:
        return VisionEscalationDecision(VisionEscalationMode.SKIP, reason_code)
    mode_available = {
        VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES: candidate_verification_available,
        VisionEscalationMode.DISCOVER_VISUAL_ENTITIES: discovery_available,
        VisionEscalationMode.DIAGNOSE_POSTCONDITION: diagnosis_available,
    }[requested_mode]
    if mode_available is None:
        mode_available = visual_available
    if not visual_available or not mode_available:
        return VisionEscalationDecision(
            VisionEscalationMode.UNAVAILABLE,
            "visual_capability_unavailable",
            evidence_need,
        )
    return VisionEscalationDecision(requested_mode, reason_code, evidence_need)


def _actionable_targets_are_ambiguous(structured: SurfaceObservation) -> bool:
    actionable_ids = {binding.target_id for binding in structured.bindings}
    candidates = [
        target for target in structured.targets if target.target_id in actionable_ids
    ]
    if len(candidates) < 2:
        return False
    descriptors = [
        (target.role.casefold().strip(), target.label.casefold().strip())
        for target in candidates
    ]
    return len(set(descriptors)) < len(descriptors)


_MULTI_TARGET_PATTERN = re.compile(
    r"\b(?:all|every|each)\b|\b(?:click|select|choose)\s+(?:the\s+)?(?:shades|items|objects|targets)\b",
    re.IGNORECASE,
)
_VISUAL_VALUE_PATTERN = re.compile(
    r"\b(?:how many|count|sum|total number|calculate|addition|add up)\b",
    re.IGNORECASE,
)


def requires_multiple_visual_targets(instruction: str) -> bool:
    return bool(_MULTI_TARGET_PATTERN.search(instruction))


def _requires_visual_value_reasoning(
    structured: SurfaceObservation,
    instruction: str,
) -> bool:
    if not _VISUAL_VALUE_PATTERN.search(instruction):
        return False
    actionable = {
        target.target_id: target
        for target in structured.targets
        if target.target_id in {binding.target_id for binding in structured.bindings}
    }
    roles = {target.role.casefold().strip() for target in actionable.values()}
    primitives = {binding.primitive_action for binding in structured.bindings}
    return bool(roles & {"textbox", "input", "spinbutton"} or primitives & {"fill", "type"})
