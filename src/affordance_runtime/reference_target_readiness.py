"""Typed evidence gate for switching legacy reference scenarios to target Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.reference_scenarios import ReferenceScenario


class ReferenceTargetBlocker(StrEnum):
    """One missing product capability required by a retained scenario contract."""

    INTERACTION_EFFECT_BOUNDARY = "interaction_effect_boundary_required"
    STRUCTURAL_DOCUMENT_CONTENT = "structural_document_content_required"
    STRUCTURED_OUTPUT = "structured_output_projection_required"
    AUTHORITATIVE_HTTP_STATE = "authoritative_http_state_source_required"
    MATERIALIZED_DOWNLOAD = "materialized_download_required"
    OUTPUT_INTEGRITY = "output_integrity_evidence_required"


@dataclass(frozen=True)
class ReferenceTargetReadiness:
    scenario: ReferenceScenario
    blockers: frozenset[ReferenceTargetBlocker]
    target_acceptance_test: str = ""

    def __post_init__(self) -> None:
        if self.scenario not in {"pricing", "settings", "export"}:
            raise ValueError("reference target readiness scenario is unsupported")
        if any(not isinstance(item, ReferenceTargetBlocker) for item in self.blockers):
            raise TypeError("reference target blockers must be typed")
        if self.ready != bool(self.target_acceptance_test):
            raise ValueError(
                "ready reference scenario requires one executable target acceptance test"
            )

    @property
    def ready(self) -> bool:
        return not self.blockers


REFERENCE_TARGET_READINESS = (
    ReferenceTargetReadiness(
        "pricing",
        frozenset({
            ReferenceTargetBlocker.INTERACTION_EFFECT_BOUNDARY,
            ReferenceTargetBlocker.STRUCTURAL_DOCUMENT_CONTENT,
            ReferenceTargetBlocker.STRUCTURED_OUTPUT,
        }),
    ),
    ReferenceTargetReadiness(
        "settings",
        frozenset({ReferenceTargetBlocker.AUTHORITATIVE_HTTP_STATE}),
    ),
    ReferenceTargetReadiness(
        "export",
        frozenset({
            ReferenceTargetBlocker.MATERIALIZED_DOWNLOAD,
            ReferenceTargetBlocker.OUTPUT_INTEGRITY,
        }),
    ),
)


@dataclass(frozen=True)
class ReferenceTargetCutoverBlockedError(RuntimeError):
    readiness: tuple[ReferenceTargetReadiness, ...]

    def __post_init__(self) -> None:
        if not self.readiness or all(item.ready for item in self.readiness):
            raise ValueError("reference cutover error requires blocked readiness evidence")

    def __str__(self) -> str:
        blocked = ", ".join(
            f"{item.scenario}=[{','.join(sorted(blocker.value for blocker in item.blockers))}]"
            for item in self.readiness
            if not item.ready
        )
        return f"target reference cutover is blocked: {blocked}"


def require_reference_target_cutover_ready(
    readiness: tuple[ReferenceTargetReadiness, ...] = REFERENCE_TARGET_READINESS,
) -> None:
    """Fail closed until every retained root scenario has executable target evidence."""

    values = tuple(readiness)
    scenarios = tuple(item.scenario for item in values)
    if set(scenarios) != {"pricing", "settings", "export"} or len(scenarios) != 3:
        raise ValueError("reference target cutover requires exactly all root scenarios")
    blocked = tuple(item for item in values if not item.ready)
    if blocked:
        raise ReferenceTargetCutoverBlockedError(blocked)
