from dataclasses import replace
from time import time

import pytest

from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, Surface
from affordance_runtime.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    UnifiedRoutePlanner,
    candidate_fingerprints,
    candidate_from_affordance,
)


def _observation() -> Observation:
    return Observation("rev-1", snapshot_id="snap-1", page_revision="page-1")


def _affordance(affordance_id: str, surface: Surface, backend: str) -> Affordance:
    lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint=f"fp-{affordance_id}",
        ttl_ms=60_000,
    )
    locator = {"bid": affordance_id} if surface == Surface.DOM else {"mark_id": "M1", "bbox": [10, 20, 30, 40]}
    return Affordance(
        affordance_id,
        surface,
        "button",
        "Save",
        "click",
        locator,
        lease,
        backend_candidates=[backend],
        confidence=0.9,
    )


def test_semantic_resolver_groups_matching_dom_and_som_candidates() -> None:
    observation = _observation()
    dom = candidate_from_affordance(
        _affordance("save", Surface.DOM, "browsergym"), observation, semantic_target_id="pending"
    )
    visual = candidate_from_affordance(
        _affordance("mark-save", Surface.VISUAL, "visual"),
        observation,
        semantic_target_id="pending",
        image_size=(800, 600),
    )
    targets = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("button", "Save", "click", "settings", dom),
            CandidateDescriptor("button", "Save", "click", "settings", visual),
        )
    )

    assert len(targets) == 1
    assert {item.source for item in targets[0].grounding_candidates} == {
        GroundingSource.DOM,
        GroundingSource.SOM,
    }
    assert all(item.semantic_target_id == targets[0].semantic_target_id for item in targets[0].grounding_candidates)


def test_semantic_resolver_does_not_merge_same_label_across_containers() -> None:
    observation = _observation()
    first = candidate_from_affordance(
        _affordance("save-1", Surface.DOM, "browsergym"), observation, semantic_target_id="pending"
    )
    second = candidate_from_affordance(
        _affordance("save-2", Surface.DOM, "browsergym"), observation, semantic_target_id="pending"
    )

    targets = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("button", "Save", "click", "header", first),
            CandidateDescriptor("button", "Save", "click", "dialog", second),
        )
    )

    assert len(targets) == 2


def test_semantic_resolver_keeps_indistinguishable_same_source_siblings_ordered() -> None:
    observation = _observation()
    first = candidate_from_affordance(
        _affordance("checkbox-1", Surface.DOM, "browsergym"),
        observation,
        semantic_target_id="pending",
    )
    second = candidate_from_affordance(
        _affordance("checkbox-2", Surface.DOM, "browsergym"),
        observation,
        semantic_target_id="pending",
    )

    targets = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("checkbox", "on", "click", "form", first),
            CandidateDescriptor("checkbox", "on", "click", "form", second),
        )
    )

    assert len(targets) == 2
    assert [item.grounding_candidates[0].source_affordance_id for item in targets] == [
        "checkbox-1",
        "checkbox-2",
    ]
    assert targets[0].semantic_target_id != targets[1].semantic_target_id


def test_route_planner_applies_hard_gates_before_preferring_cheaper_dom() -> None:
    base_observation = _observation()
    dom = candidate_from_affordance(
        _affordance("save", Surface.DOM, "browsergym"), base_observation, semantic_target_id="pending"
    )
    visual = candidate_from_affordance(
        _affordance("mark-save", Surface.VISUAL, "visual"),
        base_observation,
        semantic_target_id="pending",
        image_size=(800, 600),
    )
    target = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("button", "Save", "click", "settings", dom),
            CandidateDescriptor("button", "Save", "click", "settings", visual),
        )
    )[0]
    observation = replace(base_observation, target_fingerprints=candidate_fingerprints((target,)))
    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.VISUAL, GroundingSource.SOM}),
        preferred_sources=(GroundingSource.DOM, GroundingSource.SOM),
        minimum_verifier_strength=1,
    )

    route = UnifiedRoutePlanner().plan(
        target,
        action="activate",
        requirements=requirements,
        observation=observation,
        available_executors=frozenset({"browsergym", "visual"}),
        verifier_kinds=("state_delta_or_terminal",),
    )

    assert route.selected_candidate.source == GroundingSource.DOM
    assert [item.source for item in route.viable_alternatives] == [GroundingSource.SOM]
    assert all(item.passed for item in route.hard_gate_results)


def test_unrelated_page_visual_evidence_cannot_satisfy_dom_candidate_gate() -> None:
    base_observation = _observation()
    dom = candidate_from_affordance(
        _affordance("save", Surface.DOM, "browsergym"),
        base_observation,
        semantic_target_id="pending",
    )
    target = SemanticEntityResolver().resolve((CandidateDescriptor("button", "Save", "click", "settings", dom),))[0]
    observation = replace(
        base_observation,
        screenshot_ref="unrelated-page.png",
        target_fingerprints=candidate_fingerprints((target,)),
    )

    with pytest.raises(ValueError, match="required_evidence_missing"):
        UnifiedRoutePlanner().plan(
            target,
            action="activate",
            requirements=PerceptionRequirements(
                required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
                acceptable_evidence=frozenset({GroundingSource.DOM}),
            ),
            observation=observation,
            available_executors=frozenset({"browsergym"}),
            verifier_kinds=("state_delta_or_terminal",),
        )


def test_route_planner_rejects_expired_or_unverified_candidates() -> None:
    observation = _observation()
    candidate = candidate_from_affordance(
        _affordance("save", Surface.DOM, "browsergym"), observation, semantic_target_id="pending"
    )
    target = SemanticEntityResolver().resolve((CandidateDescriptor("button", "Save", "click", "settings", candidate),))[
        0
    ]
    expired = replace(target.grounding_candidates[0], expires_at_s=time() - 1)
    target = replace(target, grounding_candidates=(expired,))
    observation = replace(observation, target_fingerprints=candidate_fingerprints((target,)))

    with pytest.raises(ValueError, match="candidate_expired"):
        UnifiedRoutePlanner().plan(
            target,
            action="activate",
            requirements=PerceptionRequirements(minimum_verifier_strength=1),
            observation=observation,
            available_executors=frozenset({"browsergym"}),
        )


def test_route_planner_excludes_failed_candidate_and_selects_fresh_alternative() -> None:
    observation = _observation()
    first = candidate_from_affordance(
        _affordance("save-dom", Surface.DOM, "browsergym"),
        observation,
        semantic_target_id="pending",
    )
    second = replace(
        candidate_from_affordance(
            _affordance("save-a11y", Surface.ACCESSIBILITY, "browsergym"),
            observation,
            semantic_target_id="pending",
        ),
        confidence=0.8,
    )
    target = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("button", "Save", "click", "settings", first),
            CandidateDescriptor("button", "Save", "click", "settings", second),
        )
    )[0]
    observation = replace(observation, target_fingerprints=candidate_fingerprints((target,)))

    route = UnifiedRoutePlanner().plan(
        target,
        action="activate",
        requirements=PerceptionRequirements(minimum_verifier_strength=0),
        observation=observation,
        available_executors=frozenset({"browsergym"}),
        excluded_candidate_ids=frozenset({target.grounding_candidates[0].candidate_id}),
    )

    assert route.selected_candidate.candidate_id == target.grounding_candidates[1].candidate_id
    excluded_gate = next(
        item for item in route.hard_gate_results if item.candidate_id == target.grounding_candidates[0].candidate_id
    )
    assert excluded_gate.passed is False
    assert excluded_gate.reasons == ("candidate_excluded",)
