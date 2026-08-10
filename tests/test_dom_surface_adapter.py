import asyncio
from typing import Any

from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionBinder, ActionSpaceBuilder, build_agent_world_view
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class InteractivePage:
    url = "http://fixture/shared"

    def __init__(self) -> None:
        self.enabled = False
        self.clicks = 0

    def content(self) -> str:
        label = "Shared state enabled" if self.enabled else "Enable shared state"
        return f"<main><button id='shared'>{label}</button></main>"

    def click(self, selector: str) -> None:
        assert selector == "#shared"
        self.clicks += 1
        self.enabled = True

    def fill(self, selector: str, value: str) -> None:
        raise AssertionError((selector, value))

    def screenshot(self, **kwargs: Any) -> bytes:
        return b"png"


class CountingBrowserSession(BrowserSession):
    def __init__(self, page: InteractivePage) -> None:
        super().__init__(page)  # type: ignore[arg-type]
        self.currentness_probes = 0

    def probe_dom_target(self, source_target_id: str) -> tuple[str, str] | None:
        self.currentness_probes += 1
        return super().probe_dom_target(source_target_id)


def test_dom_adapter_keeps_selector_private_and_executes_current_binding() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        session = CountingBrowserSession(page)
        adapter = DomSurfaceAdapter(session)
        world = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await world.reset(task)
        assert acquisition.observation is not None
        before = acquisition.observation
        view = build_agent_world_view(before)
        space = ActionSpaceBuilder().build(task, before)
        option = space.options[0]
        request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), before, "context:test")

        assert before.observation_id
        assert "selector" not in repr(view)
        assert request.binding.payload["selector"] == "#shared"
        assert world.is_current(request)
        outcome = await world.execute(request)
        result = outcome.result
        after = outcome.post_acquisition.observation
        assert after is not None

        assert result.transport_success
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert session.currentness_probes == 1
        assert page.clicks == 1
        assert after.observation_id != before.observation_id
        assert after.targets[0].label == "Shared state enabled"

    asyncio.run(scenario())


def test_stale_dom_binding_makes_zero_executor_calls() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        world = UnifiedWorldEnvironment((DomSurfaceAdapter(BrowserSession(page)),))  # type: ignore[arg-type]
        effectful = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await world.reset(effectful)
        assert acquisition.observation is not None
        old = acquisition.observation
        option = ActionSpaceBuilder().build(effectful, old).options[0]
        request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), old, "context:test")
        from affordance_runtime.world import ObservationRequestKind, WorldObservationRequest
        await world.capture(WorldObservationRequest(ObservationRequestKind.CURRENTNESS_REFRESH, "new"))

        assert not world.is_current(request)
        assert page.clicks == 0

    asyncio.run(scenario())


def test_async_dom_fingerprint_change_makes_zero_executor_calls() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        world = UnifiedWorldEnvironment((DomSurfaceAdapter(BrowserSession(page)),))  # type: ignore[arg-type]
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await world.reset(task)
        assert acquisition.observation is not None
        observed = acquisition.observation
        option = ActionSpaceBuilder().build(task, observed).options[0]
        request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), observed, "context:test")

        page.enabled = True  # DOM changes after observation, before execute.

        assert world.is_current(request)  # world/source identity is current; the adapter owns the live probe.
        result = (await world.execute(request)).result
        assert result.dispatch_status.value == "not_sent"
        assert page.clicks == 0

    asyncio.run(scenario())


def test_unsupported_dom_primitive_does_not_discard_supported_actions() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        original_content = page.content

        def content() -> str:
            return original_content() + "<a id='download' href='/report' download>Download</a>"

        page.content = content  # type: ignore[method-assign]
        world = UnifiedWorldEnvironment((DomSurfaceAdapter(BrowserSession(page)),))  # type: ignore[arg-type]
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await world.reset(task)
        assert acquisition.observation is not None
        observed = acquisition.observation
        space = ActionSpaceBuilder().build(task, observed)

        assert len(observed.targets) == 2
        assert len(space.options) == 1
        assert "download" in observed.sources[0].artifacts["unsupported_actions"]

    asyncio.run(scenario())
