from time import time

import pytest

from affordance_runtime.actions.contracts import Observation
from affordance_runtime.actions.grounding import (
    AssertionResolutionStatus,
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    SourceAssertion,
    UnifiedAffordance,
)
from affordance_runtime.actions.unified_grounding import UnifiedRoutePlanner
from affordance_runtime.surfaces.dom.browser_session import BrowserSnapshot
from affordance_runtime.surfaces.dom.document_model import DomAdapter
from affordance_runtime.world.source_assertions import (
    SourceAssertionArbiter,
    SourceAssertionOrchestrator,
)


def _observation() -> Observation:
    return Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"dom:target": "fingerprint-1"},
    )


def _assertion(
    assertion_id: str,
    *,
    property_key: str,
    value: object,
    source: GroundingSource,
    value_type: str = "boolean",
    confidence: float = 1.0,
    expires_at_s: float = 0.0,
) -> SourceAssertion:
    return SourceAssertion(
        assertion_id,
        "semantic:target",
        property_key,
        value,
        value_type,
        source,
        "snap-1",
        "rev-1",
        "page-1",
        parser_id=f"{source.value}-parser-v1",
        confidence=confidence,
        expires_at_s=expires_at_s,
        evidence_refs=(f"artifact:{assertion_id}",),
    )


def _target() -> UnifiedAffordance:
    candidate = GroundingCandidate(
        "dom:target",
        "semantic:target",
        GroundingSource.DOM,
        DomGroundingPayload(selector="#target"),
        "dom",
        "snap-1",
        "rev-1",
        "page-1",
        "fingerprint-1",
        frozenset({"activate"}),
        frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
        fingerprint_key="dom:target",
    )
    return UnifiedAffordance(
        "semantic:target",
        "button",
        "Target",
        frozenset({"activate"}),
        grounding_candidates=(candidate,),
    )


def test_source_assertion_value_is_deeply_immutable_from_source_payload() -> None:
    raw_value = {"temperature": [20]}

    assertion = SourceAssertion(
        "api-temperature",
        "semantic:target",
        "temperature",
        raw_value,
        "json",
        GroundingSource.API,
        "snap-1",
        "rev-1",
        "page-1",
        "api-parser-v1",
        evidence_refs=("artifact:temperature",),
    )

    raw_value["temperature"].append(21)

    assert assertion.value == {"temperature": [20]}
    with pytest.raises(TypeError):
        assertion.value["temperature"][0] = 21


def test_assertion_arbiter_accepts_independent_normalized_agreement() -> None:
    arbitration = SourceAssertionArbiter().arbitrate(
        (
            _assertion("wot", property_key="power", value="on", source=GroundingSource.WOT),
            _assertion("api", property_key="power", value=True, source=GroundingSource.API),
        ),
        _observation(),
    )

    decision = arbitration.decisions[0]
    assert decision.status == AssertionResolutionStatus.ACCEPTED
    assert decision.accepted_assertion is not None
    assert {item.source for item in decision.assertions} == {
        GroundingSource.WOT,
        GroundingSource.API,
    }


def test_property_authority_beats_unrelated_cross_source_confidence() -> None:
    arbitration = SourceAssertionArbiter().arbitrate(
        (
            _assertion(
                "dom-color",
                property_key="color",
                value="blue",
                value_type="string",
                source=GroundingSource.DOM,
                confidence=0.99,
            ),
            _assertion(
                "visual-color",
                property_key="color",
                value="red",
                value_type="string",
                source=GroundingSource.VISUAL,
                confidence=0.6,
            ),
        ),
        _observation(),
    )

    decision = arbitration.decisions[0]
    assert decision.status == AssertionResolutionStatus.ACCEPTED
    assert decision.accepted_assertion_id == "visual-color"
    assert "visual evidence" in decision.reason


def test_material_same_authority_conflict_requests_bounded_reobservation() -> None:
    assertions = (
        _assertion("dom-true", property_key="checked", value=True, source=GroundingSource.DOM),
        _assertion("dom-false", property_key="checked", value=False, source=GroundingSource.DOM),
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        assertions,
        _observation(),
        available_sources=frozenset({GroundingSource.DOM, GroundingSource.ACCESSIBILITY}),
        observation_budget=1,
    )

    assert arbitration.decisions[0].status == AssertionResolutionStatus.REOBSERVE
    assert len(arbitration.active_perception_requests) == 1
    assert arbitration.active_perception_requests[0].max_observations == 1
    assert arbitration.active_perception_requests[0].requested_sources == (
        GroundingSource.DOM,
        GroundingSource.ACCESSIBILITY,
    )


def test_conflicting_authoritative_wot_and_api_state_requires_reobservation() -> None:
    arbitration = SourceAssertionArbiter().arbitrate(
        (
            _assertion("wot-on", property_key="power", value=True, source=GroundingSource.WOT),
            _assertion("api-off", property_key="power", value=False, source=GroundingSource.API),
        ),
        _observation(),
        available_sources=frozenset({GroundingSource.WOT, GroundingSource.API}),
        observation_budget=1,
    )

    assert arbitration.decisions[0].status == AssertionResolutionStatus.REOBSERVE
    assert arbitration.active_perception_requests[0].requested_sources == (
        GroundingSource.WOT,
        GroundingSource.API,
    )


def test_stale_assertions_are_inconclusive_when_reobserve_budget_is_exhausted() -> None:
    arbitration = SourceAssertionArbiter().arbitrate(
        (
            _assertion(
                "expired",
                property_key="visible",
                value=True,
                source=GroundingSource.DOM,
                expires_at_s=time() - 1,
            ),
        ),
        _observation(),
        observation_budget=0,
    )

    assert arbitration.decisions[0].status == AssertionResolutionStatus.INCONCLUSIVE
    assert not arbitration.active_perception_requests


def test_orchestrator_binds_accepted_state_and_route_blocks_unresolved_conflict() -> None:
    assertions = (
        _assertion("dom-true", property_key="checked", value=True, source=GroundingSource.DOM),
        _assertion("dom-false", property_key="checked", value=False, source=GroundingSource.DOM),
        _assertion(
            "visual-color",
            property_key="color",
            value="Red",
            value_type="string",
            source=GroundingSource.VISUAL,
        ),
    )
    targets, arbitration = SourceAssertionOrchestrator().reconcile(
        (_target(),),
        assertions,
        _observation(),
        available_sources=frozenset(
            {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.VISUAL}
        ),
        observation_budget=1,
    )

    target = targets[0]
    assert dict(target.accepted_state)["color"] == "Red"
    assert target.unresolved_conflicts == ("checked:reobserve",)
    assert len(arbitration.active_perception_requests) == 1
    with pytest.raises(ValueError, match="unresolved material conflicts"):
        UnifiedRoutePlanner().plan(
            target,
            action="activate",
            requirements=PerceptionRequirements(),
            observation=_observation(),
            available_executors=frozenset({"dom"}),
            verifier_kinds=("state_delta_or_terminal",),
        )


def test_assertion_observation_budget_limits_requests_across_properties() -> None:
    assertions = (
        _assertion("checked-true", property_key="checked", value=True, source=GroundingSource.DOM),
        _assertion("checked-false", property_key="checked", value=False, source=GroundingSource.DOM),
        _assertion(
            "color-red",
            property_key="color",
            value="red",
            value_type="string",
            source=GroundingSource.VISUAL,
        ),
        _assertion(
            "color-blue",
            property_key="color",
            value="blue",
            value_type="string",
            source=GroundingSource.VISUAL,
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        assertions,
        _observation(),
        available_sources=frozenset(
            {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.VISUAL}
        ),
        observation_budget=1,
    )

    assert len(arbitration.active_perception_requests) == 1
    assert [item.status for item in arbitration.decisions] == [
        AssertionResolutionStatus.REOBSERVE,
        AssertionResolutionStatus.CONFLICT,
    ]


def test_orchestrator_attaches_arbitration_to_one_coherent_snapshot() -> None:
    observation = _observation()
    snapshot = BrowserSnapshot(
        observation,
        DomAdapter().transduce(
            "<button id='target'>Target</button>",
            environment_revision="rev-1",
            snapshot_id="snap-1",
            page_revision="page-1",
        ),
        unified_affordances=(_target(),),
    )
    assertions = (
        _assertion("dom-true", property_key="checked", value=True, source=GroundingSource.DOM),
        _assertion("dom-false", property_key="checked", value=False, source=GroundingSource.DOM),
    )

    reconciled = SourceAssertionOrchestrator().reconcile_snapshot(
        snapshot,
        assertions,
        available_sources=frozenset({GroundingSource.DOM, GroundingSource.ACCESSIBILITY}),
    )

    assert reconciled.source_assertions == assertions
    assert reconciled.assertion_decisions[0].status == AssertionResolutionStatus.REOBSERVE
    assert reconciled.active_perception_requests[0].entity_key == "semantic:target"
    assert reconciled.unified_affordances[0].unresolved_conflicts == ("checked:reobserve",)
