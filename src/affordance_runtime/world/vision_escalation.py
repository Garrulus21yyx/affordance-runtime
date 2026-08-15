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
    if _actionable_targets_are_ambiguous(structured):
        return (VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,)
    return ()


def _actionable_targets_are_ambiguous(structured: SurfaceObservation) -> bool:
    actionable_ids = {binding.target_id for binding in structured.bindings}
    candidates = [
        target for target in structured.targets if target.target_id in actionable_ids
    ]
    if len(candidates) < 2:
        return False
    descriptors = [_public_disambiguation_descriptor(target) for target in candidates]
    return len(set(descriptors)) < len(descriptors)


def _public_disambiguation_descriptor(target) -> tuple[object, ...]:
    within = target.relations.get("within")
    if isinstance(within, dict):
        within_value: object = tuple(sorted((str(key), repr(value)) for key, value in within.items()))
    else:
        within_value = repr(within)
    return (
        target.role.casefold().strip(),
        target.label.casefold().strip(),
        tuple(sorted((str(key), repr(value)) for key, value in target.state.items())),
        within_value,
        tuple(
            sorted(
                (str(key), repr(value))
                for key, value in target.relations.items()
                if key != "within"
            )
        ),
    )
