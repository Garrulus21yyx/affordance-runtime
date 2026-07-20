"""Backend selection adapted from the earlier modular action system.

The old repository mixed smart-room skill names with routing policy. This
module retains the measured cost/reliability/latency scoring while accepting
planner-neutral affordance candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from affordance_runtime.contracts import Affordance, ExecutionReceipt


@dataclass
class BackendStats:
    attempts: int = 0
    successes: int = 0
    total_latency_ms: float = 0.0

    @property
    def reliability(self) -> float:
        return self.successes / self.attempts if self.attempts else 1.0

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / self.attempts if self.attempts else 0.0


@dataclass
class BackendConfidenceTracker:
    stats: dict[str, BackendStats] = field(default_factory=dict)

    def update(self, backend: str, *, success: bool, latency_ms: float) -> None:
        current = self.stats.setdefault(backend, BackendStats())
        current.attempts += 1
        current.successes += int(success)
        current.total_latency_ms += max(0.0, latency_ms)

    def observe_receipt(self, receipt: ExecutionReceipt) -> None:
        self.update(receipt.backend, success=receipt.success, latency_ms=receipt.latency_ms)

    def get(self, backend: str) -> BackendStats:
        return self.stats.get(backend, BackendStats())


@dataclass(frozen=True)
class RoutingDecision:
    selected_backend: str | None
    candidate_backends: list[str]
    scores: dict[str, float]
    reason: str
    confidence: float = 0.0


@dataclass
class CostAwareRouter:
    """Select the lowest-scoring viable backend.

    Lower cost, lower latency, and higher observed reliability are preferred.
    The router only proposes a backend; the contract builder still binds the
    final backend and the runtime still performs policy and preflight checks.
    """

    tracker: BackendConfidenceTracker = field(default_factory=BackendConfidenceTracker)
    costs: dict[str, float] = field(default_factory=lambda: {"wot": 0.1, "dom": 0.3, "visual": 1.0})
    cost_weight: float = 0.4
    reliability_weight: float = 0.4
    latency_weight: float = 0.2
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

        weight_sum = self.cost_weight + self.reliability_weight + self.latency_weight
        if weight_sum <= 0:
            raise ValueError("routing weights must sum to a positive value")

        preferred = set(preferred_backends)
        scores: dict[str, float] = {}
        for backend in viable:
            stats = self.tracker.get(backend)
            latency = min(stats.mean_latency_ms / self.latency_normalizer_ms, 1.0)
            score = (
                self.cost_weight * self.costs.get(backend, 0.5)
                + self.reliability_weight * (1.0 - stats.reliability)
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
            reason=f"selected lowest cost/reliability/latency score: {selected}",
            confidence=candidates[selected].confidence,
        )

    def observe(self, receipt: ExecutionReceipt) -> None:
        self.tracker.observe_receipt(receipt)
