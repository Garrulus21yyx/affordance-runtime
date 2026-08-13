from __future__ import annotations

from affordance_runtime.task import ScopeEntityDomain, ScopeExtent, ScopeSpec
from affordance_runtime.task.scope_enumerator import SnapshotScopeEnumerator
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldObservation,
)


def _world(*, dom: CoverageState, visual: CoverageState | None = None) -> WorldObservation:
    target = SemanticTarget("entity:one", "generic", "")
    structural = SurfaceObservation(
        "source:dom",
        "dom",
        "revision:dom",
        ObservationSourceProfile.dom(),
        (target,),
        coverage=dom,
    )
    sources = [structural]
    coverage = {"dom": dom}
    if visual is not None:
        sources.append(
            SurfaceObservation(
                "source:visual",
                "visual",
                "revision:visual",
                ObservationSourceProfile.visual(),
                (target,),
                coverage=visual,
            )
        )
        coverage["visual"] = visual
    return WorldObservation(
        "observation:scope",
        (target,),
        (),
        (),
        coverage,
        sources=tuple(sources),
    )


def _scope(domain: ScopeEntityDomain, extent=ScopeExtent.CURRENT_VIEWPORT) -> ScopeSpec:
    return ScopeSpec("scope:held-out", "current-viewport", extent, entity_domain=domain)


def test_scope_owner_distinguishes_structured_visual_and_fused_closure() -> None:
    enumerator = SnapshotScopeEnumerator()
    structural_only = _world(dom=CoverageState.COMPLETE)
    both = _world(dom=CoverageState.COMPLETE, visual=CoverageState.COMPLETE)

    assert enumerator.enumerate(_scope(ScopeEntityDomain.STRUCTURED), structural_only).coverage.value == "complete"
    assert enumerator.enumerate(_scope(ScopeEntityDomain.ALL_VISIBLE), structural_only).coverage.value == "partial"
    assert enumerator.enumerate(_scope(ScopeEntityDomain.FUSED), structural_only).coverage.value == "partial"
    assert enumerator.enumerate(_scope(ScopeEntityDomain.FUSED), both).coverage.value == "complete"


def test_snapshot_owner_never_certifies_larger_scope() -> None:
    result = SnapshotScopeEnumerator().enumerate(
        _scope(ScopeEntityDomain.STRUCTURED, ScopeExtent.CURRENT_DOCUMENT),
        _world(dom=CoverageState.COMPLETE),
    )

    assert result.coverage.value == "partial"
    assert result.continuation_required is True
    assert result.evidence_refs == ()
