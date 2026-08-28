"""Pure evidence-gated visual acquisition decisions.

Provider availability is a capability, never evidence that Vision should run.
The decision consumes only the current structured observation and explicit
runtime facts; it performs no acquisition or model I/O.
"""

from __future__ import annotations

from enum import StrEnum

from affordance_runtime.world.contracts import SurfaceObservation


class VisionEvidenceNeed(StrEnum):
    """The bounded kind of evidence missing from the structured control plane."""

    NONE = "none"
    RAW_SCREENSHOT = "raw_screenshot"
    OPEN_WORLD_ENTITY_DISCOVERY = "open_world_entity_discovery"
    SINGLE_TARGET_DISAMBIGUATION = "single_target_disambiguation"
    POSTCONDITION_DIAGNOSIS = "postcondition_diagnosis"


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
        return (VisionEvidenceNeed.RAW_SCREENSHOT,)
    if postcondition_unresolved:
        return (VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS,)
    if "unresolved_visual_layer_transition" in structured.artifacts:
        return (VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS,)
    # Generic structural truncation records the limits of the current source;
    # it does not identify a visual question.  The sole ActionPolicy must first
    # request one bounded visual purpose.  Runtime may still add the explicit
    # post-action layer obligation above because that is a typed transition
    # fact, not a guess based on page size, candidate count, or task language.
    return ()
