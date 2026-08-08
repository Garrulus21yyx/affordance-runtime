"""Deterministic readiness for bounded semantic criterion evaluation."""

from enum import StrEnum

from affordance_runtime.evaluation.criterion_contracts import NormalizedCriterionSpec
from affordance_runtime.model_boundary.evaluator_views import SemanticJudgeRequest
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.source_profile import assurance_satisfies


class SemanticReadiness(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    INCONCLUSIVE = "inconclusive"


def assess_semantic_readiness(
    criterion: NormalizedCriterionSpec,
    request: SemanticJudgeRequest,
    observation: WorldObservation,
) -> SemanticReadiness:
    window = next(
        (item for item in request.evidence_windows if item.criterion_id == criterion.criterion_id),
        None,
    )
    relevant = tuple(
        item for item in request.evidence_catalog.items
        if (
            item.kind == "fact" and item.subject_id in criterion.evidence_scope_target_ids
            or item.kind == "artifact" and item.output_id in criterion.evidence_scope_output_ids
        )
        and (
            not criterion.required_assurance
            or assurance_satisfies(item.assurance, criterion.required_assurance)
        )
    )
    if relevant:
        return SemanticReadiness.READY
    if window is not None and window.eligible_count > 0:
        return SemanticReadiness.INCONCLUSIVE
    if window is not None and window.eligible_count > window.visible_count:
        return SemanticReadiness.INCONCLUSIVE
    complete = bool(observation.coverage) and all(
        item == CoverageState.COMPLETE for item in observation.coverage.values()
    )
    return SemanticReadiness.NOT_READY if complete else SemanticReadiness.INCONCLUSIVE
