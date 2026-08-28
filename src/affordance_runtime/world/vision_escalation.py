"""Pure evidence-gated visual acquisition decisions.

Provider availability is a capability, never evidence that Vision should run.
The decision consumes only the current structured observation and explicit
runtime facts; it performs no acquisition or model I/O.
"""

from __future__ import annotations

from enum import StrEnum

from affordance_runtime.world.contracts import CoverageState, SurfaceObservation


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
    # A bounded structural omission is a Runtime-owned fact. Candidate count,
    # duplicate labels, and task-language similarity are not: they require the
    # policy to first state what it intends to interact with. Consequently,
    # single-target disambiguation is admitted only as an explicit typed need,
    # never inferred here before the policy has selected an action intent.
    if structured.coverage is CoverageState.TRUNCATED:
        return (VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY,)
    return ()
