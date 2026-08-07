import asyncio
from typing import Any

from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.execution.contracts import ActionIntent
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
        return f"<main><button id='shared' data-runtime-effect-class='shared_state_enabled'>{label}</button></main>"

    def click(self, selector: str) -> None:
        assert selector == "#shared"
        self.clicks += 1
        self.enabled = True

    def fill(self, selector: str, value: str) -> None:
        raise AssertionError((selector, value))

    def screenshot(self, **kwargs: Any) -> bytes:
        return b"png"


def test_dom_adapter_keeps_selector_private_and_executes_current_binding() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        adapter = DomSurfaceAdapter(BrowserSession(page))  # type: ignore[arg-type]
        world = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        await world.reset(task)
        before = await world.observe("initial")
        view = build_agent_world_view(before)
        space = ActionSpaceBuilder().build(task, before)
        option = space.options[0]
        request = ActionBinder().bind(ActionIntent(option.semantic_action, option.target_id), before)

        assert before.observation_id
        assert "selector" not in repr(view)
        assert request.binding.payload["selector"] == "#shared"
        assert world.is_current(request)
        result = await world.execute(request)
        after = await world.observe("post action")

        assert result.transport_success
        assert page.clicks == 1
        assert after.observation_id != before.observation_id
        assert after.targets[0].label == "Shared state enabled"

    asyncio.run(scenario())


def test_stale_dom_binding_makes_zero_executor_calls() -> None:
    async def scenario() -> None:
        page = InteractivePage()
        world = UnifiedWorldEnvironment((DomSurfaceAdapter(BrowserSession(page)),))  # type: ignore[arg-type]
        task = TaskGoal("read", "Inspect shared state")
        await world.reset(task)
        old = await world.observe("old")
        effectful = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        option = ActionSpaceBuilder().build(effectful, old).options[0]
        request = ActionBinder().bind(ActionIntent(option.semantic_action, option.target_id), old)
        await world.observe("new")

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
        await world.reset(task)
        observed = await world.observe("initial")
        option = ActionSpaceBuilder().build(task, observed).options[0]
        request = ActionBinder().bind(ActionIntent(option.semantic_action, option.target_id), observed)

        page.enabled = True  # DOM changes after observation, before execute.

        assert not world.is_current(request)
        assert page.clicks == 0

    asyncio.run(scenario())
