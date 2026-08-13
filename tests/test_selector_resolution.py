from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.task.scope_enumerator import ScopeEnumeration
from affordance_runtime.task.selector_resolution import (
    SelectorResolutionDisposition,
    install_selector_visual_leaf_assessments,
    resolve_entity_selector,
)
from affordance_runtime.task.set_objective import (
    FactEquals,
    PredicateTruth,
    ScopeCoverage,
    VisualConcept,
)
from affordance_runtime.world import CoverageState, SemanticTarget, WorldObservation


@dataclass(frozen=True)
class _ClosedScope:
    def enumerate(self, scope, observation):
        return ScopeEnumeration(
            scope.scope_id,
            observation.observation_id,
            tuple(item.target_id for item in observation.targets),
            ScopeCoverage.COMPLETE,
            ("fixture:closed-scope",),
        )


def _world(epoch: int) -> WorldObservation:
    return WorldObservation(
        f"observation:{epoch}",
        (
            SemanticTarget("entity:a", "button", "A", {"kind": "candidate"}),
            SemanticTarget("entity:b", "button", "B", {"kind": "candidate"}),
        ),
        (),
        (),
        {"fixture": CoverageState.COMPLETE},
    )


def test_structural_and_visual_selectors_share_one_resolution_state_machine() -> None:
    world = _world(1)
    structural = resolve_entity_selector(
        "selector:structural",
        FactEquals("identity.label", "B"),
        world,
        enumerator=_ClosedScope(),
    )
    leaf = VisualConcept("held-out fruit")
    visual = resolve_entity_selector(
        "selector:visual",
        leaf,
        world,
        enumerator=_ClosedScope(),
    )

    assert structural.disposition is SelectorResolutionDisposition.RESOLVED
    assert structural.resolved_entity_id == "entity:b"
    assert visual.disposition is SelectorResolutionDisposition.NEED_EVIDENCE

    resolved = install_selector_visual_leaf_assessments(
        visual,
        world,
        leaf,
        (
            ("entity:a", PredicateTruth.FALSE),
            ("entity:b", PredicateTruth.TRUE),
        ),
        evaluator_id="fixture:classifier",
        enumerator=_ClosedScope(),
    )

    assert resolved.disposition is SelectorResolutionDisposition.RESOLVED
    assert resolved.resolved_entity_id == "entity:b"
    assert all(item.confidence is None for item in resolved.semantic_leaf_assessments)


def test_selector_evidence_is_observation_bound_and_never_reused_after_refresh() -> None:
    leaf = VisualConcept("held-out fruit")
    first = resolve_entity_selector(
        "selector:visual",
        leaf,
        _world(1),
        enumerator=_ClosedScope(),
    )
    first = install_selector_visual_leaf_assessments(
        first,
        _world(1),
        leaf,
        (
            ("entity:a", PredicateTruth.TRUE),
            ("entity:b", PredicateTruth.FALSE),
        ),
        evaluator_id="fixture:classifier",
        enumerator=_ClosedScope(),
    )
    refreshed = resolve_entity_selector(
        "selector:visual",
        leaf,
        _world(2),
        enumerator=_ClosedScope(),
        semantic_leaf_assessments=first.semantic_leaf_assessments,
    )

    assert refreshed.disposition is SelectorResolutionDisposition.NEED_EVIDENCE
    assert refreshed.semantic_leaf_assessments == ()
