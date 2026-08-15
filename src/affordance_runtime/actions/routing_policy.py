"""Pluggable ranking policy for candidates that already passed hard gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.actions.grounding import GroundingCandidate, RouteScore


@dataclass(frozen=True)
class RouteContext:
    latency_budget_ms: int
    cost_budget: float
    preferred_rank: int
    verified_failure_rate: float | None = None


class RoutePolicy(Protocol):
    def score(self, candidate: GroundingCandidate, context: RouteContext) -> RouteScore: ...


@dataclass(frozen=True)
class WeightedRoutePolicy:
    confidence_weight: float = 0.6
    latency_weight: float = 0.2
    cost_weight: float = 0.2
    verification_weight: float = 0.4

    def __post_init__(self) -> None:
        if min(
            self.confidence_weight,
            self.latency_weight,
            self.cost_weight,
            self.verification_weight,
        ) < 0:
            raise ValueError("route policy weights cannot be negative")
        if not any(
            (
                self.confidence_weight,
                self.latency_weight,
                self.cost_weight,
                self.verification_weight,
            )
        ):
            raise ValueError("route policy requires at least one positive weight")

    def score(self, candidate: GroundingCandidate, context: RouteContext) -> RouteScore:
        confidence_component = 1.0 - candidate.confidence
        latency_component = min(candidate.expected_latency_ms / max(context.latency_budget_ms, 1), 1.0)
        cost_denominator = context.cost_budget if context.cost_budget > 0 else 1.0
        cost_component = min(candidate.expected_cost / cost_denominator, 1.0)
        verification_component = (
            0.5 if context.verified_failure_rate is None else context.verified_failure_rate
        )
        score = (
            self.confidence_weight * confidence_component
            + self.latency_weight * latency_component
            + self.cost_weight * cost_component
            + self.verification_weight * verification_component
            + context.preferred_rank * 0.01
        )
        return RouteScore(
            candidate.candidate_id,
            round(score, 6),
            round(confidence_component, 6),
            round(latency_component, 6),
            round(cost_component, 6),
            round(verification_component, 6),
        )
