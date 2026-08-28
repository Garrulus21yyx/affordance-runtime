import asyncio
from typing import Any

from affordance_runtime.actions import (
    ActionBinder,
    ActionSpaceBuilder,
)
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.world_projection import project_model_world as _project_model_world
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.canonical_world import canonical_world


def project_model_world(observation, budget, *args, **kwargs):
    return _project_model_world(observation, budget, *args, canonical_projection=canonical_world(observation), **kwargs)


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


class RepeatedControlsPage(InteractivePage):
    def content(self) -> str:
        return "<main><button id='first'>Show</button><button id='second'>Show</button></main>"


class ReadablePage(RepeatedControlsPage):
    def evaluate(self, expression: str) -> object:
        if "document.activeElement" in expression:
            return ""
        if "innerText" in expression:
            return "OpenAI\nOpenAI is an American artificial intelligence research organization."
        return {}


class TruncatedReadablePage(ReadablePage):
    def evaluate(self, expression: str) -> object:
        if "innerText" in expression:
            return "A" * 33_000
        return super().evaluate(expression)


class FramedPage(InteractivePage):
    frames = (object(), object())


class DialogPage(InteractivePage):
    def content(self) -> str:
        return (
            '<main><button id="shared">Search</button></main>'
            '<div role="dialog" aria-modal="true" aria-label="Sign in">'
            '<button id="challenge">Show QR code</button></div>'
        )


class GeometricOverlayPage(ReadablePage):
    def content(self) -> str:
        return '<main><button id="shared">Continue with QR</button></main>'

    def evaluate(self, expression: str) -> object:
        if "runtimeLayerProbe" in expression:
            return [
                {
                    "layer_id": "layer:0",
                    "kind": "geometric_overlay",
                    "role": "region",
                    "label": "Scan the visible QR code",
                    "text": "Scan the visible QR code with the Taobao app",
                    "modal": False,
                    "bbox": [100, 50, 600, 500],
                    "member_keys": ["#shared"],
                }
            ]
        return super().evaluate(expression)


class BlockingOverlayPage(ReadablePage):
    def content(self) -> str:
        return '<main><button id="shared">Search</button></main>'

    def evaluate(self, expression: str) -> object:
        if "runtimeLayerProbe" in expression:
            return [
                {
                    "layer_id": "layer:0",
                    "kind": "geometric_overlay",
                    "role": "region",
                    "label": "Visible overlay",
                    "text": "",
                    "modal": False,
                    "bbox": [0, 0, 800, 600],
                    "member_keys": [],
                    "occluded_keys": ["#shared"],
                }
            ]
        return super().evaluate(expression)


class AppearingBlockingOverlayPage(BlockingOverlayPage):
    def __init__(self) -> None:
        super().__init__()
        self.overlay_visible = False

    def evaluate(self, expression: str) -> object:
        if "runtimeLayerProbe" in expression and not self.overlay_visible:
            return []
        if "runtimeTargetHitTest" in expression:
            return not self.overlay_visible
        return super().evaluate(expression)


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
        view = project_model_world(before, ContextProjectionBudget())
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
        assert next(target for target in after.targets if target.role == "button").label == ("Shared state enabled")
        assert any(target.role == "browser_context" for target in after.targets)

    asyncio.run(scenario())


def test_dom_live_probe_not_parser_lease_owns_execution_currentness() -> None:
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
        observed = acquisition.observation
        option = ActionSpaceBuilder().build(task, observed).options[0]
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            observed,
            "context:slow-model",
        )

        assert request.binding.expires_at_s == 0.0
        await asyncio.sleep(0.01)
        assert world.is_current(request)
        result = (await world.execute(request)).result

        assert result.transport_success
        assert session.currentness_probes == 1
        assert page.clicks == 1

    asyncio.run(scenario())


def test_dom_capture_order_disambiguates_identical_executable_controls() -> None:
    async def scenario() -> None:
        page = RepeatedControlsPage()
        task = TaskGoal(
            "repeated-controls",
            "Activate one visible control",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None
        observed = acquired.observation

        source = observed.sources[0]
        show_target_ids = {target.target_id for target in observed.targets if target.label == "Show"}
        show_nodes = tuple(node for node in source.structure if node.semantic_target_id in show_target_ids)
        projection = canonical_world(
            observed,
            ActionSpaceBuilder().build(task, observed),
        )
        show_records = tuple(
            record
            for record in projection.ordered_target_records
            if record.label == "Show" and record.ref.startswith("E")
        )

        assert len(show_nodes) == 2
        assert len({node.structure_id for node in show_nodes}) == 2
        assert len(show_records) == 2
        assert len({record.ref for record in show_records}) == 2

    asyncio.run(scenario())


def test_dom_structure_preserves_active_dialog_layer_without_visual_provider() -> None:
    async def scenario() -> None:
        page = DialogPage()
        task = TaskGoal(
            "dialog-layer",
            "Prepare the visible sign-in challenge",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None
        source = acquired.observation.sources[0]
        dialog = next(node for node in source.structure if node.role == "dialog")
        challenge = next(target for target in source.targets if target.label == "Show QR code")
        challenge_node = next(node for node in source.structure if node.semantic_target_id == challenge.target_id)
        index = canonical_world(
            acquired.observation,
            ActionSpaceBuilder().build(task, acquired.observation),
        )

        assert dialog.label == "Sign in"
        assert dialog.state["active_layer"] is True
        assert challenge_node.parent_structure_id == dialog.structure_id
        challenge_record = next(
            record for record in index.ordered_target_records if record.target_id == challenge.target_id
        )
        assert any(region.role == "dialog" for region in index.ordered_region_records)
        assert "dialog" in challenge_record.structural_slot

    asyncio.run(scenario())


def test_dom_structure_preserves_browser_observed_geometric_layer_and_membership() -> None:
    async def scenario() -> None:
        page = GeometricOverlayPage()
        task = TaskGoal(
            "geometric-layer",
            "Prepare the current visible challenge",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None
        source = acquired.observation.sources[0]
        layer = next(target for target in source.targets if target.state.get("active_layer") is True)
        control = next(target for target in source.targets if target.label == "Continue with QR")
        layer_node = next(node for node in source.structure if node.semantic_target_id == layer.target_id)
        control_node = next(node for node in source.structure if node.semantic_target_id == control.target_id)

        assert layer.state["layer_kind"] == "geometric_overlay"
        assert layer.state["visible_text"] == "Scan the visible QR code with the Taobao app"
        assert control.relations["parent_id"] == layer.target_id
        assert control_node.parent_structure_id == layer_node.structure_id

    asyncio.run(scenario())


def test_active_overlay_withholds_occluded_control_from_current_action_space() -> None:
    async def scenario() -> None:
        page = BlockingOverlayPage()
        task = TaskGoal(
            "blocking-layer",
            "Handle the current visible overlay",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        world = UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        )
        acquired = await world.reset(task)
        assert acquired.observation is not None
        observed = acquired.observation
        layer = next(target for target in observed.targets if target.state.get("active_layer") is True)
        blocked = next(target for target in observed.targets if target.label == "Search")
        space = ActionSpaceBuilder().build(task, observed)
        index = WorldDeliveryIndex.from_observation(observed, space.options)
        layer_region = index.region_for_target(layer.target_id)

        assert blocked.state["interaction_blocked"] is True
        assert blocked.state["blocked_by_active_layer"] == layer.target_id
        assert layer.state["blocks_background"] is True
        assert layer.state["blocked_control_count"] == 1
        assert all(option.target_id != blocked.target_id for option in space.options)
        assert any(option.target_id == "browser-context:current" for option in space.options)
        assert layer_region is not None
        assert layer_region.state_badges == {
            "active_layer": True,
            "blocks_background": True,
            "blocked_control_count": 1,
            "modal": False,
        }

    asyncio.run(scenario())


def test_new_overlay_invalidates_previously_observed_background_binding_before_dispatch() -> None:
    async def scenario() -> None:
        page = AppearingBlockingOverlayPage()
        task = TaskGoal(
            "overlay-currentness",
            "Use the visible Search control",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        world = UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        )
        acquired = await world.reset(task)
        assert acquired.observation is not None
        observed = acquired.observation
        search = next(target for target in observed.targets if target.label == "Search")
        option = next(
            item for item in ActionSpaceBuilder().build(task, observed).options if item.target_id == search.target_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            observed,
            "context:overlay-currentness",
        )

        page.overlay_visible = True

        # The World identity is still current, while the execution owner must
        # reject the now-occluded live route before transport dispatch.
        assert world.is_current(request)
        result = (await world.execute(request)).result
        assert result.dispatch_status.value == "not_sent"
        assert result.error == "stale_binding"
        assert page.clicks == 0

    asyncio.run(scenario())


def test_dom_visible_text_enters_the_existing_readable_world_contract() -> None:
    async def scenario() -> None:
        page = ReadablePage()
        task = TaskGoal(
            "read-visible-text",
            "Report the first sentence",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None
        observed = acquired.observation
        readable = tuple(target for target in observed.targets if target.role == "StaticText")
        index = canonical_world(
            observed,
            ActionSpaceBuilder().build(task, observed),
        )

        assert [target.label for target in readable] == [
            "OpenAI",
            "OpenAI is an American artificial intelligence research organization.",
        ]
        assert any(node.label == "Visible page text" for node in observed.sources[0].structure)
        assert any(record.label == readable[1].label for record in index.ordered_target_records)

    asyncio.run(scenario())


def test_dom_visible_text_reports_honest_source_and_record_truncation() -> None:
    async def scenario() -> None:
        page = TruncatedReadablePage()
        task = TaskGoal(
            "read-truncated-text",
            "Read a bounded real page",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(page)),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None
        source = acquired.observation.sources[0]
        readable = tuple(target for target in source.targets if target.role == "StaticText")

        assert source.coverage.value == "truncated"
        assert readable
        assert readable[-1].state["semantic.accessible_name.truncated"] is True

    asyncio.run(scenario())


def test_dom_main_document_reports_partial_coverage_when_child_frames_are_unprojected() -> None:
    async def scenario() -> None:
        task = TaskGoal(
            "framed-page",
            "Use a control that may be inside a child frame",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        acquired = await UnifiedWorldEnvironment(
            (
                DomSurfaceAdapter(BrowserSession(FramedPage())),  # type: ignore[arg-type]
            )
        ).reset(task)
        assert acquired.observation is not None

        source = acquired.observation.sources[0]
        assert source.coverage.value == "truncated"

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

        assert sum(target.role != "browser_context" for target in observed.targets) == 2
        assert any(target.role == "browser_context" for target in observed.targets)
        assert len(space.options) == 1
        assert "download" in observed.sources[0].artifacts["unsupported_actions"]

    asyncio.run(scenario())
