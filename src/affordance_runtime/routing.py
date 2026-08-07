"""Static backend selection for one already-grounded affordance.

Adaptive cross-source routing belongs to the verifier-backed RouteCalibrator;
this narrow selector deliberately has no receipt-success learning interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from affordance_runtime.contracts import Affordance
from affordance_runtime.immutable import FrozenSequence, freeze_json


@dataclass(frozen=True)
class RoutingDecision:
    selected_backend: str | None
    candidate_backends: list[str]
    scores: dict[str, float]
    reason: str
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_backends", FrozenSequence(self.candidate_backends))
        object.__setattr__(self, "scores", freeze_json(self.scores))


@dataclass
class CostAwareRouter:
    """Select the lowest-scoring viable backend from configured static priors.

    The router only proposes a backend; the contract builder still binds the
    final backend and the runtime still performs policy and preflight checks.
    Runtime outcomes cannot update this object.
    """

    costs: dict[str, float] = field(default_factory=lambda: {"wot": 0.1, "dom": 0.3, "visual": 1.0})
    expected_latency_ms: dict[str, float] = field(
        default_factory=lambda: {"wot": 100.0, "dom": 150.0, "visual": 1_000.0}
    )
    cost_weight: float = 0.7
    latency_weight: float = 0.3
    latency_normalizer_ms: float = 2_000.0
    preferred_bonus: float = 0.05

    def route(
        self,
        candidates: Mapping[str, Affordance],
        *,
        allowed_backends: set[str] | None = None,
        preferred_backends: tuple[str, ...] = (),
        excluded_backends: set[str] | None = None,
    ) -> RoutingDecision:
        allowed = set(candidates) if allowed_backends is None else allowed_backends
        excluded = excluded_backends or set()
        viable = [name for name in candidates if name in allowed and name not in excluded]
        if not viable:
            return RoutingDecision(None, [], {}, "no viable backend")

        weight_sum = self.cost_weight + self.latency_weight
        if weight_sum <= 0:
            raise ValueError("routing weights must sum to a positive value")

        preferred = set(preferred_backends)
        scores: dict[str, float] = {}
        for backend in viable:
            latency = min(
                max(0.0, self.expected_latency_ms.get(backend, self.latency_normalizer_ms))
                / self.latency_normalizer_ms,
                1.0,
            )
            score = (
                self.cost_weight * self.costs.get(backend, 0.5)
                + self.latency_weight * latency
            ) / weight_sum
            if backend in preferred:
                score -= self.preferred_bonus
            scores[backend] = score

        ordered = sorted(viable, key=lambda name: (scores[name], name))
        selected = ordered[0]
        return RoutingDecision(
            selected_backend=selected,
            candidate_backends=ordered,
            scores={name: round(scores[name], 4) for name in ordered},
            reason=f"selected lowest configured cost/latency score: {selected}",
            confidence=candidates[selected].confidence,
        )
