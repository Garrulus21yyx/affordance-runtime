import asyncio
import hashlib
from dataclasses import replace

import pytest

from affordance_runtime.surfaces.visual import VisualFrame, VisualSurfaceAdapter, VisualViewport
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.visual_grounding import VisualRegion
from affordance_runtime.world import ActionBinder, ActionSpaceBuilder, build_agent_world_view
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


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

    def propose(self, request):
        del request
        return [VisualRegion(self.bbox, "Shared state", 0.95, True, "button", self.primitive)]


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )


async def _bound(session: VisualSession, proposer: Proposer):
    adapter = VisualSurfaceAdapter(session, proposer)  # type: ignore[arg-type]
    world = UnifiedWorldEnvironment((adapter,))
    task = _task()
    await world.reset(task)
    observed = await world.observe("initial")
    option = ActionSpaceBuilder().build(task, observed).options[0]
    request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), observed)
    return adapter, world, observed, request


def test_visual_adapter_keeps_coordinates_private_and_uses_one_probe_and_pointer_call() -> None:
    async def scenario() -> None:
        session = VisualSession()
        _, world, observed, request = await _bound(session, Proposer())

        assert "action_point" not in repr(build_agent_world_view(observed))
        assert request.binding.payload["action_point_xy"] == (40.0, 40.0)
        result = await world.execute(request)

        assert result.transport_success
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert session.captures == 2
        assert session.clicks == [(40, 40)]

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
        lambda session, proposer: setattr(proposer, "bbox", (0.25, 0.25, 0.4, 0.5)),
    ],
)
def test_visual_currentness_changes_are_not_sent(mutate) -> None:
    async def scenario() -> None:
        session, proposer = VisualSession(), Proposer()
        _, world, _, request = await _bound(session, proposer)
        mutate(session, proposer)

        result = await world.execute(request)

        assert result.dispatch_status.value == "not_sent"
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

        result = await world.execute(request)
        assert result.error.value == "invalid_parameters"
        assert session.clicks == []

    asyncio.run(scenario())


def test_visual_pointer_exception_is_sent_unknown_without_retry() -> None:
    async def scenario() -> None:
        session = VisualSession()
        session.fail_click = True
        _, world, _, request = await _bound(session, Proposer())

        result = await world.execute(request)
        assert result.dispatch_status.value == "sent_unknown"
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert len(session.clicks) == 1

    asyncio.run(scenario())


def test_reset_invalidates_old_visual_request_without_probe_or_pointer_call() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter, world, _, request = await _bound(session, Proposer())
        await adapter.reset(_task())

        result = await world.execute(request)
        assert result.dispatch_status.value == "not_sent"
        assert result.adapter_evidence["currentness_probe_count"] == 0
        assert session.captures == 1
        assert session.clicks == []

    asyncio.run(scenario())


def test_unsupported_visual_primitive_retains_target_without_action() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter = VisualSurfaceAdapter(session, Proposer("drag"))  # type: ignore[arg-type]
        await adapter.reset(_task())
        observed = await adapter.observe("initial")

        assert len(observed.targets) == 1
        assert observed.bindings == ()
        assert observed.artifacts["unsupported_actions"] == ("drag",)

    asyncio.run(scenario())
