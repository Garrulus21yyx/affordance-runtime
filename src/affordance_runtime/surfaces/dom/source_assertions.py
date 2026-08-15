"""DOM snapshot projection of generic world assertion arbitration."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from affordance_runtime.actions.grounding import GroundingSource, SourceAssertion
from affordance_runtime.surfaces.dom.browser_session import BrowserSnapshot
from affordance_runtime.world.source_assertions import SourceAssertionOrchestrator


def reconcile_browser_snapshot(
    snapshot: BrowserSnapshot,
    assertions: Iterable[SourceAssertion],
    *,
    available_sources: frozenset[GroundingSource] = frozenset(),
    observation_budget: int = 1,
) -> BrowserSnapshot:
    claims = tuple(assertions)
    targets, arbitration = SourceAssertionOrchestrator().reconcile(
        snapshot.unified_affordances,
        claims,
        snapshot.observation,
        available_sources=available_sources,
        observation_budget=observation_budget,
    )
    return replace(
        snapshot,
        unified_affordances=targets,
        source_assertions=claims,
        assertion_decisions=arbitration.decisions,
        active_perception_requests=arbitration.active_perception_requests,
    )
