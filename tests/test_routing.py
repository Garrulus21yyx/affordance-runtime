import pytest

from affordance_runtime.contracts import Affordance, AffordanceLease, Surface
from affordance_runtime.routing import CostAwareRouter, RoutingDecision


def _affordance(backend: str, confidence: float = 1.0) -> Affordance:
    surface = {"dom": Surface.DOM, "visual": Surface.VISUAL, "wot": Surface.WOT}[backend]
    return Affordance(
        id=f"{backend}_target",
        surface=surface,
        role="button",
        label="Target",
        action="click",
        locator={"selector": "#target"},
        lease=AffordanceLease.issue(environment_revision="rev-1"),
        backend_candidates=[backend],
        confidence=confidence,
    )


def test_router_prefers_low_cost_reliable_backend() -> None:
    router = CostAwareRouter()
    decision = router.route({"dom": _affordance("dom"), "wot": _affordance("wot")})

    assert decision.selected_backend == "wot"
    assert decision.candidate_backends == ["wot", "dom"]


def test_routing_decision_payloads_are_immutable_from_source_collections() -> None:
    candidate_backends = ["dom"]
    scores = {"dom": 0.3}
    decision = RoutingDecision(
        selected_backend="dom",
        candidate_backends=candidate_backends,
        scores=scores,
        reason="selected",
    )

    candidate_backends.append("visual")
    scores["dom"] = 1.0

    assert decision.candidate_backends == ["dom"]
    assert decision.scores["dom"] == 0.3
    with pytest.raises(AttributeError):
        decision.candidate_backends.append("visual")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        decision.scores["dom"] = 1.0


def test_static_backend_router_has_no_receipt_success_learning_channel() -> None:
    router = CostAwareRouter(
        costs={"dom": 0.3, "wot": 0.1},
        expected_latency_ms={"dom": 100, "wot": 2_000},
        cost_weight=0.2,
        latency_weight=0.8,
    )

    decision = router.route({"dom": _affordance("dom"), "wot": _affordance("wot")})

    assert decision.selected_backend == "dom"
    assert not hasattr(router, "observe")
    assert not hasattr(router, "tracker")


def test_router_honors_allowed_and_excluded_backends() -> None:
    router = CostAwareRouter()
    decision = router.route(
        {"dom": _affordance("dom"), "visual": _affordance("visual")},
        allowed_backends={"dom", "visual"},
        excluded_backends={"dom"},
    )

    assert decision.selected_backend == "visual"
