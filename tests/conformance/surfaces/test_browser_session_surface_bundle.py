from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image

from affordance_runtime.actions import ActionBinder, ActionSpaceBuilder
from affordance_runtime.surfaces.browser_bundle import (
    BrowserSessionSurfaceBundle,
    browser_surface_from_environment,
)
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.surfaces.visual.grounding import VisualGroundingPoint, VisualRegion
from affordance_runtime.surfaces.visual.predicate_classification import (
    PredicateTruth,
    VisualPredicateClassification,
)
from affordance_runtime.surfaces.visual.semantic_classification import (
    VisualLayerAssessment,
    VisualLayerRole,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationAssurance,
    ObservationModality,
    ObservationNeed,
    ObservationPurpose,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.observation_outcomes import (
    ObservationQueryDisposition,
    VisualUnknownReason,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class _Page:
    url = "https://fixture.invalid/ui"

    def __init__(self) -> None:
        self.screenshot_calls = 0

    def content(self) -> str:
        return "<main><button id='shared'>Shared</button></main>"

    def screenshot(self, **_kwargs) -> bytes:
        self.screenshot_calls += 1
        output = BytesIO()
        Image.new("RGB", (200, 100), "white").save(output, format="PNG")
        return output.getvalue()

    def evaluate(self, script: str):
        if "runtimeCoordinateProbe" in script or "scrollX" in script:
            return {
                "width": 200,
                "height": 100,
                "scrollX": 0,
                "scrollY": 0,
                "dpr": 1,
                "zoom": 1,
                "orientation": "landscape",
            }
        if "Object.fromEntries" in script:
            return {
                "#shared": {
                    "visible": True,
                    "bbox": [10, 10, 80, 30],
                    "value": "",
                    "selected_options": [],
                    "checked": None,
                    "aria_selected": "",
                    "aria_expanded": "",
                    "aria_controls": "",
                }
            }
        if "document.activeElement" in script:
            return ""
        if "document.body?.innerText" in script:
            return "Shared"
        raise AssertionError(script)

    def click(self, selector: str) -> None:
        assert selector == "#shared"


class _Session(BrowserSession):
    def __init__(self, page: _Page) -> None:
        super().__init__(page)  # type: ignore[arg-type]
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1


class _OverlayPage(_Page):
    def __init__(self) -> None:
        super().__init__()
        self.overlay = False

    def screenshot(self, **_kwargs) -> bytes:
        self.screenshot_calls += 1
        output = BytesIO()
        image = Image.new("RGB", (200, 100), "white")
        if self.overlay:
            from PIL import ImageDraw

            ImageDraw.Draw(image).rectangle((40, 15, 160, 85), fill="gray")
        image.save(output, format="PNG")
        return output.getvalue()

    def evaluate(self, script: str):
        if "runtimeLayerProbe" in script:
            if not self.overlay:
                return []
            return [
                {
                    "layer_id": "layer:0",
                    "kind": "geometric_overlay",
                    "role": "region",
                    "label": "Continue in the visible challenge",
                    "text": "Continue in the visible challenge",
                    "modal": False,
                    "bbox": [40, 15, 120, 70],
                    "member_keys": ["#shared"],
                }
            ]
        return super().evaluate(script)

    def click(self, selector: str) -> None:
        super().click(selector)
        self.overlay = True


@dataclass
class _Proposer:
    calls: list[object] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def propose(self, request):
        self.calls.append(request)
        return [VisualRegion((0.05, 0.1, 0.4, 0.3), "Shared", 0.9)]


@dataclass
class _Predicate:
    calls: list[object] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def classify(self, request):
        self.calls.append(request)
        return tuple(VisualPredicateClassification(item.ref, PredicateTruth.TRUE, 0.91) for item in request.candidates)


@dataclass
class _Grounder:
    calls: list[object] = field(default_factory=list)

    def ground(self, request):
        self.calls.append(request)
        return VisualGroundingPoint((0.5, 0.5), normalized=True)


@dataclass
class _LayerObserver:
    calls: list[object] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def observe_layers(self, request):
        self.calls.append(request)
        return tuple(
            VisualLayerAssessment(
                candidate.ref,
                "A sign-in dialog with a visible QR challenge",
                VisualLayerRole.DIALOG,
                True,
                0.93,
            )
            for candidate in request.candidates
        )


@dataclass
class _UnknownLayerObserver(_LayerObserver):
    def observe_layers(self, request):
        self.calls.append(request)
        return tuple(
            VisualLayerAssessment(
                candidate.ref,
                None,
                VisualLayerRole.UNKNOWN,
                None,
                0.2,
            )
            for candidate in request.candidates
        )


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Inspect the current control",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def test_grouped_browser_bundle_uses_one_reset_and_one_shared_frame() -> None:
    async def scenario() -> None:
        page, proposer, classifier = _Page(), _Proposer(), _Predicate()
        session = _Session(page)
        bundle = BrowserSessionSurfaceBundle(
            session,
            proposer,
            predicate_classifier=classifier,
        )
        world = UnifiedWorldEnvironment((bundle,))
        initial = await world.reset(_task())
        assert initial.observation is not None
        subject_id = next(item.target_id for item in initial.observation.targets if item.role == "button")
        assert session.reset_calls == 1
        assert page.screenshot_calls == 0
        assert proposer.calls == []
        request = WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "classify current visual state",
            (
                ObservationNeed(
                    "observation-query:product-predicate",
                    ObservationPurpose.VISUAL_PROPERTY,
                    (subject_id,),
                    ObservationModality.VISUAL,
                    ObservationAssurance.WEAK,
                    evidence_property="visually selected",
                    query_text="visually selected",
                ),
            ),
        )
        acquired = await world.capture(request)
        assert acquired.observation is not None
        assert page.screenshot_calls == 1
        assert len(classifier.calls) == 1
        assert proposer.calls == []
        sources = {item.surface: item for item in acquired.observation.sources}
        assert set(sources) == {"dom", "visual"}
        assert sources["dom"].acquisition_root_id == sources["visual"].acquisition_root_id
        assert sources["dom"].media[0].sha256 == sources["visual"].media[0].sha256
        outcome = acquired.query_outcome("observation-query:product-predicate")
        assert outcome is not None
        assert outcome.observed_subject_ids

    asyncio.run(scenario())


def test_new_geometric_overlay_gets_one_bounded_visual_layer_observation() -> None:
    async def scenario() -> None:
        page, proposer, observer = _OverlayPage(), _Proposer(), _LayerObserver()
        bundle = BrowserSessionSurfaceBundle(
            _Session(page),
            proposer,
            layer_observer=observer,
        )
        world = UnifiedWorldEnvironment((bundle,))
        task = _task()
        initial = await world.reset(task)
        assert initial.observation is not None
        button_id = next(target.target_id for target in initial.observation.targets if target.role == "button")
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, initial.observation).options
            if item.target_id == button_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            initial.observation,
            "context:overlay",
        )

        execution = await world.execute(request)

        assert execution.post_acquisition is not None
        assert execution.post_acquisition.observation is not None
        after = execution.post_acquisition.observation
        assert len(observer.calls) == 1
        assert proposer.calls == []
        assert page.screenshot_calls == 2
        assert {source.surface for source in after.sources} == {"dom", "visual"}
        layer = next(target for target in after.targets if target.state.get("active_layer") is True)
        facts = {fact.predicate: fact.value for fact in after.facts if fact.subject_id == layer.target_id}
        assert facts["visual_change"] == "appeared"
        assert facts["visual_layer_role"] == "dialog"
        assert facts["occludes_primary_surface"] is True

    asyncio.run(scenario())


def test_ordinary_structural_action_keeps_visual_layer_provider_at_zero_calls() -> None:
    async def scenario() -> None:
        page, proposer, observer = _Page(), _Proposer(), _LayerObserver()
        bundle = BrowserSessionSurfaceBundle(
            _Session(page),
            proposer,
            layer_observer=observer,
        )
        world = UnifiedWorldEnvironment((bundle,))
        task = _task()
        initial = await world.reset(task)
        assert initial.observation is not None
        button_id = next(target.target_id for target in initial.observation.targets if target.role == "button")
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, initial.observation).options
            if item.target_id == button_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            initial.observation,
            "context:ordinary",
        )

        execution = await world.execute(request)

        assert execution.post_acquisition is not None
        assert execution.post_acquisition.observation is not None
        assert observer.calls == []
        assert proposer.calls == []
        assert page.screenshot_calls == 1
        assert {source.surface for source in execution.post_acquisition.observation.sources} == {"dom"}

    asyncio.run(scenario())


def test_preexisting_geometric_overlay_is_not_reobserved_as_a_new_transition() -> None:
    async def scenario() -> None:
        page, observer = _OverlayPage(), _LayerObserver()
        page.overlay = True
        bundle = BrowserSessionSurfaceBundle(
            _Session(page),
            _Proposer(),
            layer_observer=observer,
        )
        world = UnifiedWorldEnvironment((bundle,))
        task = _task()
        initial = await world.reset(task)
        assert initial.observation is not None
        button_id = next(target.target_id for target in initial.observation.targets if target.role == "button")
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, initial.observation).options
            if item.target_id == button_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            initial.observation,
            "context:preexisting-overlay",
        )

        execution = await world.execute(request)

        assert execution.post_acquisition is not None
        assert observer.calls == []
        assert {source.surface for source in execution.post_acquisition.observation.sources} == {"dom"}  # type: ignore[union-attr]

    asyncio.run(scenario())


def test_indeterminate_overlay_returns_typed_unknown_without_guessing() -> None:
    async def scenario() -> None:
        page, observer = _OverlayPage(), _UnknownLayerObserver()
        bundle = BrowserSessionSurfaceBundle(
            _Session(page),
            _Proposer(),
            layer_observer=observer,
        )
        world = UnifiedWorldEnvironment((bundle,))
        task = _task()
        initial = await world.reset(task)
        assert initial.observation is not None
        button_id = next(target.target_id for target in initial.observation.targets if target.role == "button")
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, initial.observation).options
            if item.target_id == button_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            initial.observation,
            "context:unknown-overlay",
        )

        execution = await world.execute(request)

        assert execution.post_acquisition is not None
        outcome = execution.post_acquisition.query_outcome("residual:effect_verification")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.UNKNOWN
        assert outcome.unknown_items[0].reason is VisualUnknownReason.CHANGE_NOT_DETERMINABLE
        assert len(observer.calls) == 1
        assert not any(
            fact.predicate == "visual_layer_description"
            for fact in execution.post_acquisition.observation.facts  # type: ignore[union-attr]
        )

    asyncio.run(scenario())


def test_viewport_drift_rejects_layer_observation_before_calling_visual_provider() -> None:
    class DriftPage(_OverlayPage):
        def evaluate(self, script: str):
            if "runtimeCoordinateProbe" in script or "scrollX" in script:
                return {
                    "width": 201 if self.overlay else 200,
                    "height": 100,
                    "scrollX": 0,
                    "scrollY": 0,
                    "dpr": 1,
                    "zoom": 1,
                    "orientation": "landscape",
                }
            return super().evaluate(script)

    async def scenario() -> None:
        page, observer = DriftPage(), _LayerObserver()
        bundle = BrowserSessionSurfaceBundle(
            _Session(page),
            _Proposer(),
            layer_observer=observer,
        )
        world = UnifiedWorldEnvironment((bundle,))
        task = _task()
        initial = await world.reset(task)
        assert initial.observation is not None
        button_id = next(target.target_id for target in initial.observation.targets if target.role == "button")
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, initial.observation).options
            if item.target_id == button_id
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            initial.observation,
            "context:viewport-drift",
        )

        execution = await world.execute(request)

        assert execution.post_acquisition is not None
        outcome = execution.post_acquisition.query_outcome("residual:effect_verification")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.UNKNOWN
        assert observer.calls == []

    asyncio.run(scenario())


def test_grouped_world_screenshot_does_not_invoke_semantic_visual_provider() -> None:
    async def scenario() -> None:
        page, proposer = _Page(), _Proposer()
        world = UnifiedWorldEnvironment((BrowserSessionSurfaceBundle(_Session(page), proposer),))
        await world.reset(_task())

        acquired = await world.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "capture auxiliary screenshot evidence",
                (
                    ObservationNeed(
                        "observation-query:world-screenshot",
                        ObservationPurpose.WORLD_GROUNDING,
                        required_modality=ObservationModality.VISUAL,
                    ),
                ),
            )
        )

        assert acquired.observation is not None
        assert proposer.calls == []
        visual = next(item for item in acquired.observation.sources if item.surface == "visual")
        assert visual.targets == ()
        assert len(visual.media) == 1

    asyncio.run(scenario())


def test_grouped_point_grounding_invokes_only_the_point_provider() -> None:
    async def scenario() -> None:
        page, proposer, grounder = _Page(), _Proposer(), _Grounder()
        bundle = BrowserSessionSurfaceBundle(_Session(page), proposer, point_grounder=grounder)
        world = UnifiedWorldEnvironment((bundle,))
        await world.reset(_task())

        acquired = await world.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "locate one visible target",
                (
                    ObservationNeed(
                        "observation-query:point",
                        ObservationPurpose.POINT_GROUNDING,
                        required_modality=ObservationModality.VISUAL,
                        query_text="the visible shared control",
                    ),
                ),
            )
        )

        assert acquired.observation is not None
        assert proposer.calls == []
        assert len(grounder.calls) == 1
        assert acquired.query_outcome("observation-query:point") is not None

    asyncio.run(scenario())


def test_product_browser_composition_is_dom_only_without_explicit_visual_profile() -> None:
    surface = browser_surface_from_environment(_Session(_Page()), {})
    assert isinstance(surface, DomSurfaceAdapter)


def test_product_browser_composition_uses_official_deepseek_vision_model() -> None:
    surface = browser_surface_from_environment(
        _Session(_Page()),
        {
            "LLM_VISUAL_PROFILE": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "fixture-secret",
            "LLM_DEEPSEEK_VISION_MODEL": "deepseek-v4-flash-vision-exp",
        },
    )
    assert isinstance(surface, BrowserSessionSurfaceBundle)
    assert surface.region_proposer.model == "deepseek-v4-flash-vision-exp"
    assert surface.point_grounder is not None
    assert surface.point_grounder.model == "deepseek-v4-flash-vision-exp"
    assert surface.predicate_classifier is not None
    assert surface.predicate_classifier.model == "deepseek-v4-flash-vision-exp"
    assert surface.layer_observer is not None
    assert surface.layer_observer.model == "deepseek-v4-flash-vision-exp"
