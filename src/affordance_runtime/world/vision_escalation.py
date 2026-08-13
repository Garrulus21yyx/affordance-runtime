"""Pure evidence-gated visual acquisition decisions.

Provider availability is a capability, never evidence that Vision should run.
The decision consumes only the current structured observation and explicit
runtime facts; it performs no acquisition or model I/O.
"""

from __future__ import annotations

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


def derive_visual_evidence_needs(
    structured: SurfaceObservation,
    *,
    explicitly_requested: bool = False,
    terminal: bool = False,
    postcondition_unresolved: bool = False,
) -> tuple[VisionEvidenceNeed, ...]:
    """Derive typed evidence obligations from current Runtime facts only."""

    if terminal:
        return ()
    if explicitly_requested:
        return (VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY,)
    if postcondition_unresolved:
        return (VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS,)
    if not structured.bindings:
        return (VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY,)
    if _actionable_targets_are_ambiguous(structured):
        return (VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,)
    return ()


def decide_visual_escalation(
    evidence_needs: tuple[VisionEvidenceNeed, ...],
    *,
    visual_available: bool,
    candidate_verification_available: bool | None = None,
    discovery_available: bool | None = None,
    diagnosis_available: bool | None = None,
    marked_candidate_policy_available: bool = False,
) -> VisionEscalationDecision:
    """Route typed evidence obligations to one optional visual capability."""

    if not evidence_needs:
        return VisionEscalationDecision(
            VisionEscalationMode.SKIP,
            "structured_evidence_sufficient",
        )
    evidence_need = evidence_needs[0]
    if evidence_need is VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY:
        requested_mode = VisionEscalationMode.DISCOVER_VISUAL_ENTITIES
        reason_code = "open_world_entity_discovery_required"
    elif evidence_need is VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS:
        requested_mode = VisionEscalationMode.DIAGNOSE_POSTCONDITION
        reason_code = "postcondition_visual_diagnosis"
    elif evidence_need is VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION:
        if marked_candidate_policy_available:
            return VisionEscalationDecision(
                VisionEscalationMode.SKIP,
                "marked_candidate_choice_delegated_to_screenshot_policy",
                VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
            )
        requested_mode = VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES
        reason_code = "structured_candidates_ambiguous"
    else:
        return VisionEscalationDecision(
            VisionEscalationMode.UNAVAILABLE,
            "unsupported_visual_evidence_need",
            evidence_need,
        )
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
