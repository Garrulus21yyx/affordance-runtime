from dataclasses import replace
from time import time

from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    DomGroundingPayload,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    RouteScore,
    UnifiedAffordance,
)
from affordance_runtime.memory import BindingCache, BindingCacheKey
from affordance_runtime.route_calibration import (
    RouteOutcome,
    RouteOutcomeStatus,
    RouteScope,
)
from affordance_runtime.routing_policy import RouteContext
from affordance_runtime.unified_grounding import UnifiedRoutePlanner
from affordance_runtime.verification.mechanical import VerificationStatus


def _candidate(
    candidate_id: str,
    source: GroundingSource,
    *,
    snapshot_id: str,
    fingerprint: str,
    executor: str,
) -> GroundingCandidate:
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id="semantic:save",
        source=source,
        payload=DomGroundingPayload(selector=f"#{candidate_id}"),
        compatible_executor=executor,
        observation_epoch_id=snapshot_id,
        environment_revision="rev-1",
        page_revision="page-1",
        target_fingerprint=fingerprint,
        fingerprint_key=candidate_id,
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset(),
        expires_at_s=time() + 60,
    )


class PreferVisualPolicy:
    def score(self, candidate: GroundingCandidate, context: RouteContext) -> RouteScore:
        del context
        score = 0.0 if candidate.source == GroundingSource.VISUAL else 1.0
        return RouteScore(candidate.candidate_id, score, 0, 0, 0)


def test_route_policy_only_ranks_candidates_that_passed_hard_gates() -> None:
    dom = _candidate("dom", GroundingSource.DOM, snapshot_id="snap-1", fingerprint="fp-dom", executor="dom")
    visual = _candidate(
        "visual",
        GroundingSource.VISUAL,
        snapshot_id="stale-snapshot",
        fingerprint="fp-visual",
        executor="visual",
    )
    target = UnifiedAffordance(
        "semantic:save",
        "button",
        "Save",
        frozenset({"activate"}),
        grounding_candidates=(dom, visual),
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"dom": "fp-dom", "visual": "fp-visual"},
    )

    route = UnifiedRoutePlanner(policy=PreferVisualPolicy()).plan(
        target,
        action="activate",
        requirements=PerceptionRequirements(),
        observation=observation,
        available_executors=frozenset({"dom", "visual"}),
    )

    assert route.selected_candidate.candidate_id == "dom"
    assert next(item for item in route.hard_gate_results if item.candidate_id == "visual").reasons == (
        "candidate_stale",
    )


def test_binding_cache_recalls_only_fresh_regrounded_matching_fingerprint() -> None:
    key = BindingCacheKey("task:save", "semantic:save", "activate", "settings-ui")
    original = _candidate(
        "dom-original",
        GroundingSource.DOM,
        snapshot_id="snap-1",
        fingerprint="stable-fingerprint",
        executor="dom",
    )
    outcome = RouteOutcome(
        outcome_id="outcome-1",
        scope=RouteScope("settings-ui", "activate", GroundingSource.DOM, "dom", ("dom_contains",)),
        semantic_target_id="semantic:save",
        candidate_id="dom-original",
        contract_id="contract-1",
        status=RouteOutcomeStatus.VERIFIED_SUCCESS,
        verification_status=VerificationStatus.PASSED,
        evidence_ids=("evidence-1",),
        post_snapshot_id="post-1",
    )
    cache = BindingCache()
    cache.remember(key, original, outcome)
    regrounded = _candidate(
        "dom-regrounded",
        GroundingSource.DOM,
        snapshot_id="snap-2",
        fingerprint="stable-fingerprint",
        executor="dom",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-2",
        page_revision="page-1",
        target_fingerprints={"dom-regrounded": "stable-fingerprint"},
    )

    assert cache.recall(key, (regrounded,), observation) == regrounded
    assert cache.recall(key, (original,), observation) is None
    changed = replace(regrounded, target_fingerprint="changed")
    assert cache.recall(key, (changed,), observation) is None


def test_binding_cache_refuses_unverified_or_failed_outcomes() -> None:
    key = BindingCacheKey("task:save", "semantic:save", "activate", "settings-ui")
    candidate = _candidate(
        "dom",
        GroundingSource.DOM,
        snapshot_id="snap-1",
        fingerprint="fp",
        executor="dom",
    )
    failed = RouteOutcome(
        outcome_id="outcome-failed",
        scope=RouteScope("settings-ui", "activate", GroundingSource.DOM, "dom", ("dom_contains",)),
        semantic_target_id="semantic:save",
        candidate_id="dom",
        contract_id="contract-1",
        status=RouteOutcomeStatus.VERIFIED_FAILURE,
        verification_status=VerificationStatus.FAILED,
        evidence_ids=("evidence-1",),
        post_snapshot_id="post-1",
    )

    try:
        BindingCache().remember(key, candidate, failed)
    except ValueError as exc:
        assert "verified success" in str(exc)
    else:
        raise AssertionError("failed route outcome entered binding cache")
