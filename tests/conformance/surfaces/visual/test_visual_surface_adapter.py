import asyncio
import hashlib
from dataclasses import replace

import pytest

from affordance_runtime.actions import (
    ActionBinder,
    ActionSpaceBuilder,
)
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.world_projection import project_model_world as _project_model_world
from affordance_runtime.surfaces.visual import VisualFrame, VisualSurfaceAdapter, VisualViewport
from affordance_runtime.surfaces.visual.grounding import VisualGroundingPoint, VisualRegion
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.canonical_world import canonical_world
from tests.support.observation_acquisition import acquire_observation


def project_model_world(observation, budget, *args, **kwargs):
    return _project_model_world(
        observation, budget, *args, canonical_projection=canonical_world(observation), **kwargs
    )


def _png(width: int = 100, height: int = 80, suffix: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big") + suffix


class VisualSession:
    def __init__(self) -> None:
        self.image = _png()
        self.viewport = VisualViewport(100, 80, 0, 0, 1, 1, "landscape")
        self.captures = 0
        self.clicks: list[tuple[int, int]] = []
        self.fail_click = False

    def reset(self) -> None:
        pass

    def capture_visual_frame(self, observation_id: str) -> VisualFrame:
        self.captures += 1
        digest = "sha256:" + hashlib.sha256(self.image).hexdigest()
        return VisualFrame(observation_id, digest, digest, 100, 80, self.viewport, self.image)

    def click_xy(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        if self.fail_click:
            raise RuntimeError("pointer outcome unknown")


class Proposer:
    provider = "test"
    model = "fixed"
    prompt_version = "v1"

    def __init__(self, primitive: str = "point_activate") -> None:
        self.primitive = primitive
        self.bbox = (0.2, 0.25, 0.4, 0.5)
        self.calls = 0

    def propose(self, request):
        del request
        self.calls += 1
        return [VisualRegion(self.bbox, "Shared state", 0.95, True, "button", self.primitive)]


class PointGrounder:
    provider = "test-point"
    model = "fixed"
    prompt_version = "v1"

    def __init__(self, point: tuple[float, float] = (0.4, 0.5)) -> None:
        self.calls = 0
        self.point = point

    def ground(self, request):
        del request
        self.calls += 1
        return VisualGroundingPoint(self.point, normalized=True)


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )


async def _bound(session: VisualSession, proposer: Proposer):
    adapter = VisualSurfaceAdapter(session, proposer, PointGrounder())  # type: ignore[arg-type]
    world = UnifiedWorldEnvironment((adapter,))
    task = _task()
    acquisition = await world.reset(task)
    assert acquisition.observation is not None
    observed = acquisition.observation
    option = ActionSpaceBuilder().build(task, observed).options[0]
    request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), observed, "context:test")
    return adapter, world, observed, request


def test_visual_adapter_keeps_coordinates_private_and_uses_one_probe_and_pointer_call() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer()
        _, world, observed, request = await _bound(session, proposer)

        assert "action_point" not in repr(project_model_world(observed, ContextProjectionBudget()))
        assert request.binding.payload["action_point_xy"] == (40.0, 40.0)
        result = (await world.execute(request)).result

        assert result.transport_success
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert session.captures == 3
        assert session.clicks == [(40, 40)]
        assert proposer.calls == 2

    asyncio.run(scenario())


def test_visual_adapter_uses_separate_point_grounder_for_execution_authority() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer("observe_only")
        grounder = PointGrounder((0.3, 0.4))
        adapter = VisualSurfaceAdapter(session, proposer, grounder)  # type: ignore[arg-type]
        world = UnifiedWorldEnvironment((adapter,))
        task = _task()
        acquisition = await world.reset(task)
        assert acquisition.observation is not None
        observed = acquisition.observation
        option = ActionSpaceBuilder().build(task, observed).options[0]
        request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), observed, "context:test")

        assert request.binding.payload["action_point_xy"] == (30.0, 32.0)
        result = (await world.execute(request)).result

        assert result.transport_success
        assert session.clicks == [(30, 32)]
        assert grounder.calls == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda session, proposer: setattr(session, "image", _png(suffix=b"changed")),
        lambda session, proposer: setattr(session, "viewport", replace(session.viewport, width=99)),
        lambda session, proposer: setattr(session, "viewport", replace(session.viewport, scroll_y=10)),
        lambda session, proposer: setattr(session, "viewport", replace(session.viewport, device_pixel_ratio=2)),
        lambda session, proposer: setattr(session, "viewport", replace(session.viewport, zoom=1.25)),
        lambda session, proposer: setattr(session, "viewport", replace(session.viewport, orientation="portrait")),
    ],
)
def test_visual_currentness_changes_are_not_sent(mutate) -> None:
    async def scenario() -> None:
        session, proposer = VisualSession(), Proposer()
        _, world, _, request = await _bound(session, proposer)
        mutate(session, proposer)

        result = (await world.execute(request)).result

        assert result.dispatch_status.value == "not_sent"
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert session.clicks == []

    asyncio.run(scenario())


def test_bounded_visual_proposer_reports_truncated_coverage_even_when_empty() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer()
        proposer.propose = lambda request: []  # type: ignore[method-assign]
        adapter = VisualSurfaceAdapter(session, proposer)  # type: ignore[arg-type]
        adapter.initialize_task(_task())
        await adapter.reset_physical()

        observed = await acquire_observation(adapter, "bounded empty")
        assert observed.coverage.value == "truncated"
        assert observed.targets == ()

    asyncio.run(scenario())


def test_explicitly_exhaustive_visual_proposer_may_report_complete_coverage() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer()
        proposer.acquisition_exhaustive = True
        adapter = VisualSurfaceAdapter(session, proposer)  # type: ignore[arg-type]
        adapter.initialize_task(_task())
        await adapter.reset_physical()

        observed = await acquire_observation(adapter, "exhaustive")
        assert observed.coverage.value == "complete"

    asyncio.run(scenario())


def test_visual_proposer_exceeding_region_bound_fails_closed() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer()
        region = VisualRegion((0, 0, 0.01, 0.01), "mark", 1.0)
        proposer.propose = lambda request: [region] * (request.max_regions + 1)  # type: ignore[method-assign]
        adapter = VisualSurfaceAdapter(session, proposer)  # type: ignore[arg-type]
        adapter.initialize_task(_task())
        await adapter.reset_physical()

        with pytest.raises(ValueError, match="region bound"):
            await acquire_observation(adapter, "too many")

    asyncio.run(scenario())


def test_visual_state_projection_keeps_only_bounded_semantic_values() -> None:
    async def scenario() -> None:
        session = VisualSession()
        proposer = Proposer()
        raw_state = {
            "enabled": True,
            "expanded": False,
            "value": ["bounded", 2],
            "selector": "#secret",
            "x": 10,
            "href": "https://private.invalid",
            "backend": "dom",
            "visible": {"nested": "mapping"},
        }
        proposer.propose = lambda request: [  # type: ignore[method-assign]
            VisualRegion((0.2, 0.2, 0.2, 0.2), "Shared", 1.0, state=raw_state)
        ]
        adapter = VisualSurfaceAdapter(session, proposer)  # type: ignore[arg-type]
        world = UnifiedWorldEnvironment((adapter,))
        acquisition = await world.reset(_task())
        assert acquisition.observation is not None
        observed = acquisition.observation
        assert observed.targets[0].state == {
            "enabled": True,
            "expanded": False,
            "value": ["bounded", 2],
        }
        assert "selector" not in repr(project_model_world(observed, ContextProjectionBudget()))

    asyncio.run(scenario())


def test_pre_pointer_capture_failure_is_currentness_unavailable() -> None:
    async def scenario() -> None:
        session = VisualSession()
        _, world, _, request = await _bound(session, Proposer())
        session.capture_visual_frame = lambda observation_id: (_ for _ in ()).throw(  # type: ignore[method-assign]
            RuntimeError("capture unavailable")
        )

        result = (await world.execute(request)).result
        assert result.dispatch_status.value == "not_sent"
        assert result.error.value == "currentness_unavailable"
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert session.clicks == []

    asyncio.run(scenario())


def test_visual_action_point_outside_viewport_is_not_sent() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter, world, _, request = await _bound(session, Proposer())
        region = adapter._regions[request.binding.binding_id]
        adapter._regions[request.binding.binding_id] = replace(
            region,
            bbox_xywh=(120, 10, 20, 20),
            action_point_xy=(130, 20),
        )

        result = (await world.execute(request)).result
        assert result.error.value == "invalid_parameters"
        assert session.clicks == []

    asyncio.run(scenario())


def test_visual_pointer_exception_is_sent_unknown_without_retry() -> None:
    async def scenario() -> None:
        session = VisualSession()
        session.fail_click = True
        _, world, _, request = await _bound(session, Proposer())

        result = (await world.execute(request)).result
        assert result.dispatch_status.value == "sent_unknown"
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert len(session.clicks) == 1

    asyncio.run(scenario())


def test_reset_invalidates_old_visual_request_without_probe_or_pointer_call() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter, world, _, request = await _bound(session, Proposer())
        adapter.initialize_task(_task())
        await adapter.reset_physical()

        result = (await world.execute(request)).result
        assert result.dispatch_status.value == "not_sent"
        assert result.adapter_evidence["currentness_probe_count"] == 0
        assert session.captures == 1
        assert session.clicks == []

    asyncio.run(scenario())


def test_proposer_action_claim_is_normalized_to_observation_only() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter = VisualSurfaceAdapter(session, Proposer("point_activate"))  # type: ignore[arg-type]
        adapter.initialize_task(_task())
        await adapter.reset_physical()
        observed = await acquire_observation(adapter, "initial")

        assert len(observed.targets) == 1
        assert observed.bindings == ()
        assert observed.artifacts["unsupported_actions"] == ("observe_only",)

    asyncio.run(scenario())
