from __future__ import annotations

import pytest

from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    AssertionDecision,
    AssertionResolutionStatus,
    DomGroundingPayload,
    GroundingCandidate,
    GroundingSource,
    SourceAssertion,
    UnifiedAffordance,
    WoTGroundingPayload,
)
from affordance_runtime.observation_store import InMemoryObservationStore
from affordance_runtime.perception_session import (
    CoverageCompleteness,
    CoverageStatus,
    PerceptionCapture,
    SourceCoverage,
)
from affordance_runtime.unified_observation import ConflictStatus, FactStatus


@pytest.mark.parametrize("reverse_sources", [False, True])
def test_builder_retains_multibinding_conflict_and_coverage_deterministically(
    reverse_sources: bool,
) -> None:
    observation = Observation(
        environment_revision="env-1",
        snapshot_id="capture-1",
        page_revision="page-1",
    )
    candidates = (
        GroundingCandidate(
            candidate_id="candidate:dom:lamp",
            semantic_target_id="semantic:lamp",
            source=GroundingSource.DOM,
            payload=DomGroundingPayload(selector="#lamp"),
            compatible_executor="browser",
            observation_epoch_id="capture-1",
            environment_revision="env-1",
            page_revision="page-1",
            target_fingerprint="dom-lamp",
            supported_actions=frozenset({"activate"}),
            evidence_kinds=frozenset(),
            resource_sensitivity="low",
        ),
        GroundingCandidate(
            candidate_id="candidate:wot:lamp",
            semantic_target_id="semantic:lamp",
            source=GroundingSource.WOT,
            payload=WoTGroundingPayload(
                thing_id="thing:lamp", form_index=0, operation="toggle"
            ),
            compatible_executor="wot",
            observation_epoch_id="capture-1",
            environment_revision="env-1",
            page_revision="page-1",
            target_fingerprint="wot-lamp",
            supported_actions=frozenset({"activate"}),
            evidence_kinds=frozenset(),
            resource_sensitivity="high",
        ),
    )
    assertions = (
        SourceAssertion(
            assertion_id="assertion:dom:lamp:checked",
            entity_key="semantic:lamp",
            property_key="checked",
            value=False,
            value_type="boolean",
            source=GroundingSource.DOM,
            observation_epoch_id="capture-1",
            environment_revision="env-1",
            page_revision="page-1",
            parser_id="dom",
        ),
        SourceAssertion(
            assertion_id="assertion:wot:lamp:checked",
            entity_key="semantic:lamp",
            property_key="checked",
            value=True,
            value_type="boolean",
            source=GroundingSource.WOT,
            observation_epoch_id="capture-1",
            environment_revision="env-1",
            page_revision="page-1",
            parser_id="wot",
        ),
    )
    ordered_candidates = tuple(reversed(candidates)) if reverse_sources else candidates
    ordered_assertions = tuple(reversed(assertions)) if reverse_sources else assertions
    capture = PerceptionCapture(
        observation=observation,
        semantic_targets=(
            UnifiedAffordance(
                semantic_target_id="semantic:lamp",
                role="switch",
                label="Lamp",
                supported_actions=frozenset({"activate"}),
                grounding_candidates=ordered_candidates,
            ),
        ),
        grounding_candidates=ordered_candidates,
        source_assertions=ordered_assertions,
        assertion_decisions=(
            AssertionDecision(
                entity_key="semantic:lamp",
                property_key="checked",
                status=AssertionResolutionStatus.CONFLICT,
                assertions=ordered_assertions,
                reason="material source disagreement",
            ),
        ),
        source_coverage=(
            SourceCoverage.complete(GroundingSource.DOM, captured_item_count=1),
            SourceCoverage.complete(GroundingSource.WOT, captured_item_count=1),
            SourceCoverage(
                source=GroundingSource.VISUAL,
                capture_policy_id="visual-bounded",
                captured_item_count=10,
                truncated=True,
                omitted_item_count_estimate=3,
                completeness=CoverageCompleteness.BOUNDED,
                status=CoverageStatus.ACQUISITION_TRUNCATED,
            ),
        ),
    )

    canonical = CanonicalObservationBuilder().build(capture)
    store = InMemoryObservationStore()
    ref = store.put(canonical)
    view = store.open(ref)

    target = view.targets.get("semantic:lamp")
    assert target is not None
    assert target.surfaces == (GroundingSource.DOM, GroundingSource.WOT)
    assert target.action_support[0].resource_sensitivity == "high"
    assert view.bindings.for_target("semantic:lamp") == tuple(
        sorted(candidates, key=lambda item: item.candidate_id)
    )
    assert target.conflict_status == ConflictStatus.MATERIAL_CONFLICT
    fact = view.facts.get("semantic:lamp", "checked")
    assert fact is not None and fact.status == FactStatus.CONFLICTED
    assert view.coverage.get(GroundingSource.VISUAL).status == CoverageStatus.ACQUISITION_TRUNCATED
    assert ref.digest == canonical.digest
    assert ref.epoch_id == "capture-1"

    canonical_again = CanonicalObservationBuilder().build(capture)
    assert canonical_again.digest == canonical.digest
