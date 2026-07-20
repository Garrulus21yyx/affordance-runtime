from affordance_runtime.contracts import Affordance, AffordanceLease, Surface
from affordance_runtime.routing import CostAwareRouter


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


def test_router_learns_to_avoid_failing_backend() -> None:
    router = CostAwareRouter()
    for _ in range(3):
        router.tracker.update("wot", success=False, latency_ms=500)

    decision = router.route({"dom": _affordance("dom"), "wot": _affordance("wot")})

    assert decision.selected_backend == "dom"


def test_router_honors_allowed_and_excluded_backends() -> None:
    router = CostAwareRouter()
    decision = router.route(
        {"dom": _affordance("dom"), "visual": _affordance("visual")},
        allowed_backends={"dom", "visual"},
        excluded_backends={"dom"},
    )

    assert decision.selected_backend == "visual"
