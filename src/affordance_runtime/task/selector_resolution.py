"""Shared scope/evidence lifecycle for one typed entity selector."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.task.scope_enumerator import (
    ScopeEnumeratorPort,
    SnapshotScopeEnumerator,
)
from affordance_runtime.task.set_objective import (
    CandidateUniverse,
    PredicateAssessment,
    PredicateAssurance,
    PredicateExpr,
    PredicateTruth,
    ScopeCoverage,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
    evaluate_predicate,
    predicate_digest,
    visual_predicate_leaves,
)
from affordance_runtime.task.set_objective_state import target_public_fields
from affordance_runtime.world.contracts import WorldObservation


class SelectorResolutionDisposition(StrEnum):
    NEED_SCOPE_CLOSURE = "need_scope_closure"
    NEED_EVIDENCE = "need_evidence"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class SelectorResolutionState:
    selector_id: str
    predicate: PredicateExpr
    scope: ScopeSpec
    universe: CandidateUniverse
    truth_by_entity: tuple[tuple[str, PredicateTruth], ...]
    semantic_leaf_assessments: tuple[PredicateAssessment, ...] = ()

    @property
    def disposition(self) -> SelectorResolutionDisposition:
        if self.universe.coverage is not ScopeCoverage.COMPLETE:
            return SelectorResolutionDisposition.NEED_SCOPE_CLOSURE
        if any(truth is PredicateTruth.UNKNOWN for _, truth in self.truth_by_entity):
            return SelectorResolutionDisposition.NEED_EVIDENCE
        matches = tuple(entity_id for entity_id, truth in self.truth_by_entity if truth is PredicateTruth.TRUE)
        if not matches:
            return SelectorResolutionDisposition.NO_MATCH
        if len(matches) > 1:
            return SelectorResolutionDisposition.AMBIGUOUS
        return SelectorResolutionDisposition.RESOLVED

    @property
    def resolved_entity_id(self) -> str:
        if self.disposition is not SelectorResolutionDisposition.RESOLVED:
            return ""
        return next(entity_id for entity_id, truth in self.truth_by_entity if truth is PredicateTruth.TRUE)

    @property
    def unknown_entity_ids(self) -> tuple[str, ...]:
        return tuple(entity_id for entity_id, truth in self.truth_by_entity if truth is PredicateTruth.UNKNOWN)


def resolve_entity_selector(
    selector_id: str,
    predicate: PredicateExpr,
    observation: WorldObservation,
    *,
    scope: ScopeSpec | None = None,
    enumerator: ScopeEnumeratorPort | None = None,
    semantic_leaf_assessments: tuple[PredicateAssessment, ...] = (),
) -> SelectorResolutionState:
    resolved_scope = scope or ScopeSpec(
        f"scope:selector:{predicate_digest(predicate)[:16]}",
        "current-viewport",
        ScopeExtent.CURRENT_VIEWPORT,
        entity_domain=(
            ScopeEntityDomain.ALL_VISIBLE if visual_predicate_leaves(predicate) else ScopeEntityDomain.STRUCTURED
        ),
    )
    enumeration = (enumerator or SnapshotScopeEnumerator()).enumerate(resolved_scope, observation)
    universe = CandidateUniverse(
        enumeration.scope_id,
        enumeration.observation_epoch,
        enumeration.entity_ids,
        enumeration.coverage,
        enumeration.evidence_refs,
    )
    current_leaf_evidence = tuple(
        item
        for item in semantic_leaf_assessments
        if item.observation_epoch == observation.observation_id and item.entity_id in universe.entity_ids
    )
    semantic_by_entity: dict[str, dict[str, PredicateTruth]] = {}
    for item in current_leaf_evidence:
        semantic_by_entity.setdefault(item.entity_id, {})[item.predicate_digest] = item.truth
    fields = target_public_fields(observation)
    truth = tuple(
        (
            entity_id,
            evaluate_predicate(
                predicate,
                fields.get(entity_id, {}),
                semantic_by_entity.get(entity_id),
            ),
        )
        for entity_id in universe.entity_ids
    )
    return SelectorResolutionState(
        selector_id,
        predicate,
        resolved_scope,
        universe,
        truth,
        current_leaf_evidence,
    )


def install_selector_visual_leaf_assessments(
    state: SelectorResolutionState,
    observation: WorldObservation,
    leaf: PredicateExpr,
    assessments: tuple[tuple[str, PredicateTruth], ...],
    *,
    evaluator_id: str,
    enumerator: ScopeEnumeratorPort | None = None,
) -> SelectorResolutionState:
    submitted = tuple(assessments)
    leaf_digest = predicate_digest(leaf)
    current_ids = set(state.universe.entity_ids)
    if (
        observation.observation_id != state.universe.observation_epoch
        or not submitted
        or len({entity_id for entity_id, _ in submitted}) != len(submitted)
        or any(entity_id not in current_ids for entity_id, _ in submitted)
    ):
        raise ValueError("selector visual evidence is not current and bounded")
    by_key = {(item.entity_id, item.predicate_digest): item for item in state.semantic_leaf_assessments}
    for entity_id, truth in submitted:
        by_key[(entity_id, leaf_digest)] = PredicateAssessment(
            entity_id,
            leaf_digest,
            truth,
            PredicateAssurance.SEMANTIC_UNCALIBRATED,
            evaluator_id,
            observation.observation_id,
            (f"selector-visual-leaf:{observation.observation_id}:{leaf_digest[:12]}:{entity_id}",),
            None,
        )
    return resolve_entity_selector(
        state.selector_id,
        state.predicate,
        observation,
        scope=state.scope,
        enumerator=enumerator,
        semantic_leaf_assessments=tuple(by_key.values()),
    )
